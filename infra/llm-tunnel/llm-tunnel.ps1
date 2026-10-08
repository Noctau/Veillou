# Обратный SSH-туннель для Windows: домашняя Ollama (localhost:11434) → сервер (172.30.0.1:11434).
# Сервер, пользователь и ключ — в %USERPROFILE%\.ssh\config (Host veillou-llm).
# Запуск при входе — Планировщик заданий (Docs/DEPLOY.md §6).
while ($true) {
    ssh -N `
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new `
        -R 172.30.0.1:11434:localhost:11434 veillou-llm
    Start-Sleep -Seconds 30   # связь оборвалась или сервер не готов — пробуем снова
}
