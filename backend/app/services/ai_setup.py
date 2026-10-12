"""ИИ-настройка (M21.4): описание занятости → черновик сборки.

«Настроить по описанию» ставит джобу `ai.setup`; воркер зовёт ИИ с текущей
конфигурацией как контекстом (названия кирпичей — чтобы ИИ ими пользовался),
переводит упрощённый ответ в `ConfigBundle` (`domain/bundle.normalize_setup`),
проверяет кирпичи схемой сборки и считает dry-run импорта. Ничего не меняется:
экран проверки правит черновик и шлёт его в `POST /config/import`.
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import SetupContext, setup_messages
from app.ai.schemas import AISetup
from app.core.time import get_tz, local_date, now_utc
from app.domain import bundle as dom
from app.domain.enums import AIPurpose, JobKind
from app.models import Job, User
from app.schemas.ai import SetupDraft, SetupRequest
from app.schemas.bundle import ConfigBundle, bundle_json
from app.services import jobs
from app.services.ai import call_llm, enqueue_ai
from app.services.ai_profile import load_ai_context
from app.services.bundle import BundleService


def _existing(bundle: dict[str, Any]) -> dict[str, list[str]]:
    return {s: [dom.title(s, i) for i in bundle.get(s) or []] for s in dom.SECTIONS}


def validated(raw: dict[str, Any]) -> tuple[ConfigBundle, list[str]]:
    """Сборка по схеме; кирпич, который схему не прошёл, выкидывается (с ним и те, кто
    на него ссылался), с предупреждением."""
    warnings: list[str] = []
    data = {k: list(v) if isinstance(v, list) else v for k, v in raw.items()}
    for _ in range(len(dom.SECTIONS) + 1):
        try:
            bundle = ConfigBundle.model_validate(data)
            dom.check_refs(bundle_json(bundle))
            return bundle, warnings
        except ValidationError as exc:
            bad = {(e["loc"][0], e["loc"][1]) for e in exc.errors() if len(e["loc"]) > 1}
            if not bad:
                raise
            for section, index in sorted(bad, key=lambda b: -int(b[1])):
                item = data[str(section)].pop(int(index))
                warnings.append(f"«{dom.title(str(section), item)}» не прошло проверку — пропущено")
        except dom.BundleError:
            # Ссылки на выкинутое — убираем ссылающихся
            known = {s: {i["ref"] for i in data.get(s) or []} for s in dom.SECTIONS}
            for section in dom.SECTIONS:
                keep = []
                for item in data.get(section) or []:
                    targets = [
                        (t, r)
                        for name, t in dom.REFS.get(section, {}).items()
                        for r in (
                            item.get(name) if isinstance(item.get(name), list) else [item.get(name)]
                        )
                        if r is not None
                    ]
                    if all(r in known[t] for t, r in targets):
                        keep.append(item)
                    else:
                        warnings.append(f"«{dom.title(section, item)}» ссылается на пропущенное")
                data[section] = keep
    raise ValueError("Сборка не сходится")


class AISetupService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user
        self.user_id = user.id
        self.tz = get_tz(user.timezone)

    async def start(self, data: SetupRequest) -> uuid.UUID:
        job_id = await enqueue_ai(
            self.db,
            JobKind.ai_setup,
            user_id=self.user_id,
            payload=data.model_dump(mode="json"),
        )
        await self.db.commit()
        return job_id

    async def draft(self, request: SetupRequest, job_id: uuid.UUID | None = None) -> SetupDraft:
        today = local_date(now_utc(), self.tz)
        ai = await load_ai_context(self.db, self.user, today)
        bundles = BundleService(self.db, self.user)
        current = await bundles.export()
        ctx = SetupContext(
            text=request.text,
            today=today,
            profile=ai.profile,
            existing=_existing(current.bundle),
            previous=request.previous,
            comment=request.comment,
        )
        answer = await call_llm(
            self.db, self.user_id, AIPurpose.setup, setup_messages(ctx), AISetup, job_id=job_id
        )
        result = dom.normalize_setup(answer.model_dump(mode="json"), current.bundle, today)
        bundle, dropped = validated(result.bundle)
        preview = await bundles.import_bundle(bundle, dry_run=True)
        return SetupDraft(
            text=request.text,
            about=result.about,
            bundle=bundle,
            warnings=[*result.warnings, *dropped],
            preview=preview,
        )

    async def run(self, job: Job) -> SetupDraft:
        draft = await self.draft(SetupRequest.model_validate(job.payload), job.id)
        job.result = draft.model_dump(mode="json", by_alias=True)
        return draft


async def handle_setup_job(db: AsyncSession, job: Job) -> None:
    user = await db.get(User, job.user_id)
    if user is None:
        raise jobs.JobFailedError("Пользователь удалён")
    await AISetupService(db, user).run(job)
