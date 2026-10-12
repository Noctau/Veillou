from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.ai import JobStarted, SetupRequest
from app.schemas.bundle import BundleImportResult, ConfigBundle
from app.services.ai_setup import AISetupService
from app.services.bundle import BundleService

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/export")
async def export_config(user: CurrentUser, db: SessionDep) -> ConfigBundle:
    """Вся конфигурация (сферы, занятость, расписание, режимы, лимиты, типы,
    категории, автозадачи) одной сборкой со ссылками `ref` вместо id."""
    return ConfigBundle.model_validate((await BundleService(db, user).export()).bundle)


@router.post("/import")
async def import_config(
    bundle: ConfigBundle, user: CurrentUser, db: SessionDep, dry_run: bool = True
) -> BundleImportResult:
    """Импорт сборки поверх текущей конфигурации: новое добавляется, совпадающее по
    названию обновляется, ничего не удаляется. `dry_run=true` (по умолчанию) — только
    отчёт, что добавится и изменится."""
    return await BundleService(db, user).import_bundle(bundle, dry_run=dry_run)


@router.post("/ai-setup", status_code=status.HTTP_202_ACCEPTED)
async def start_ai_setup(data: SetupRequest, user: CurrentUser, db: SessionDep) -> JobStarted:
    """«Настроить по описанию»: ИИ собирает черновик сборки (джоба `ai.setup`,
    результат — `GET /jobs/{id}`, тип `setup`). Ничего не меняется до импорта."""
    return JobStarted(job_id=await AISetupService(db, user).start(data))
