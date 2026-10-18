# Genesis

Лаборатория искусственной жизни. Долгосрочная цель — возникновение репликации,
наследственности и организации из локальной цифровой химии.
Первый спринт создаёт временный стенд готовых агентов; сейчас реализуется только среда.

## Запуск на Windows (PowerShell)

Распакуйте `Genesis` в `H:\dev\Genesis`. Диск H: не доступен облачной среде Work,
поэтому тестирование здесь проводится на Linux. Точный путь к вашему `python.exe`
внутри `H:\DEVELOPMENT` неизвестен; укажите существующий интерпретатор Python 3.11+:

```powershell
Set-Location H:\dev\Genesis
$GenesisPython = 'H:\DEVELOPMENT\python.exe' # замените, если python.exe вложен глубже
& $GenesisPython --version
& $GenesisPython -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
& .\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
& .\.venv\Scripts\python.exe -m genesis validate --config configs/archipelago.yaml
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe -m genesis run --config configs/archipelago.yaml --output runs/first
```

Активация venv не требуется; политика выполнения PowerShell не мешает запуску.
Не изменяйте общую Python-среду `H:\DEVELOPMENT`: зависимости устанавливаются в `.venv`.
Если там Python старше 3.11 или иная архитектура, нужен совместимый интерпретатор.

## Запуск на Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pytest
.venv/bin/python -m genesis run --config configs/archipelago.yaml --output runs/first
```

Для запуска без инструментов разработки используйте `requirements.lock.txt`.
Пины версий фиксируют проверенный набор зависимостей, но не являются lock-файлом
с хешами wheel для каждой ОС. Побитовая идентичность между ОС/CPU не обещается.

## CLI

```bash
python -m genesis --version
python -m genesis init --output my-world.yaml
python -m genesis validate --config my-world.yaml
python -m genesis run --config my-world.yaml --steps 1000 --seed 7 --output runs/seed7
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m build --no-isolation
```

Каталог результата должен отсутствовать: защита от перезаписи опытов. Код возврата
2 означает некорректный конфиг/путь; лог идёт в stderr, итоговый JSON — в stdout.
В каталоге запуска: разрешённый YAML, manifest с версиями/seed/кодом,
метрики JSONL, итоговые поля NPZ и summary с digest научного состояния.
Время выполнения и сведения о платформе намеренно исключены из digest.
NPZ открывается с `numpy.load(..., allow_pickle=False)`.

Это проверочный запуск среды. Возобновление, полные RNG-checkpoints, события агентов,
пакетный runner и эволюционные эксперименты ещё не реализованы (S01-3—S01-8).

## Документы

- `GENESIS_ROADMAP.md` — единственный источник статуса спринтов.
- `docs/ARCHITECTURE.md` — границы модулей и формулы модели.
- `docs/ACCEPTANCE.md` — критерии приёмки и команды проверки.
- `docs/decisions/0001-core.md` — решения и ограничения.
- `docs/PROGRESS.md` — журнал проверенных достижений.
- `experiments/s01_environment/` — сценарий и сохранённые доказательства.

Если ZIP распакован без `.git`, восстановите историю из включённого `genesis.bundle`:
`git clone genesis.bundle H:\dev\Genesis` (каталог назначения должен отсутствовать).
Если история не нужна, исходники из архива запускаются напрямую.
