# Genesis

Лаборатория искусственной жизни. Долгосрочная цель — возникновение репликации,
наследственности и организации из локальной цифровой химии.
Первый спринт создаёт временный стенд готовых агентов. Сейчас реализованы среда,
минимальные агенты, восьмилокусная наследуемая вариативность и headless batch S01-5.

## Запуск на Windows (PowerShell)

Репозиторий находится в `H:\dev\GENESIS`, Python 3.12 — в `H:\DEVELOPMENT`,
а Python 3.11 — в `H:\DEVELOPMENT\Python3.11`. Используйте отдельное окружение проекта:

```powershell
Set-Location H:\dev\GENESIS
$GenesisPython = 'H:\DEVELOPMENT\python.exe' # замените, если python.exe вложен глубже
& $GenesisPython --version
& $GenesisPython -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
& .\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
& .\.venv\Scripts\python.exe -m genesis validate --config configs/archipelago.yaml
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe -m genesis run --config configs/archipelago.yaml --output runs/first
& .\.venv\Scripts\python.exe -m genesis batch --scenario archipelago=configs/archipelago.yaml --scenario closed=configs/closed_system.yaml --seeds 0 42 2026 --jobs 2 --output runs/batch
& .\.venv\Scripts\python.exe -m genesis benchmark --config configs/archipelago.yaml --steps 500 --warmup 50 --repeats 3 --output runs/benchmark
& .\.venv\Scripts\python.exe experiments/s01_evolution/reproduce.py --output runs/evolution-check
& .\.venv\Scripts\python.exe experiments/s01_headless/reproduce.py --output runs/headless-check
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
python -m genesis batch --scenario world=my-world.yaml --seeds 0 42 2026 --jobs 2 --output runs/batch
python -m genesis benchmark --config my-world.yaml --steps 500 --warmup 50 --repeats 3 --output runs/benchmark
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

`batch` исполняет декартово произведение именованных сценариев и seeds. `--jobs 1`
запускает его последовательно, большее значение — в изолированных процессах; научный
результат не должен меняться. Общие `batch_manifest.json` и `batch_summary.json`
сохраняют план, порядок, статусы и измеренную скорость. `benchmark` измеряет чистый
цикл симуляции после warm-up; его wall-clock показатели зависят от машины.

Это проверочный запуск среды и временных готовых агентов с наследуемыми признаками.
Он подтверждает механику наследования, но не адаптацию или возникновение жизни.
Возобновление, полные RNG-checkpoints и проверка отбора ещё не реализованы (S01-6—S01-8).

## Документы

- `GENESIS_ROADMAP.md` — единственный источник статуса спринтов.
- `docs/ARCHITECTURE.md` — границы модулей и формулы модели.
- `docs/ACCEPTANCE.md` — критерии приёмки и команды проверки.
- `docs/decisions/0001-core.md` — решения и ограничения.
- `docs/decisions/0002-agent-energy.md` — правила агентов и энергетический учёт.
- `docs/decisions/0003-quantitative-genome.md` — геном, фенотип и компромиссы.
- `docs/decisions/0004-headless-batch.md` — batch, изоляция процессов и benchmark.
- `docs/PROGRESS.md` — журнал проверенных достижений.
- `experiments/s01_environment/` — сценарий и сохранённые доказательства.
- `experiments/s01_agents/` — проверка детерминизма и энергетики агентов.
- `experiments/s01_evolution/` — контроль наследования и мутационной вариативности.
- `experiments/s01_headless/` — batch-детерминизм и базовая производительность.

Если ZIP распакован без `.git`, восстановите историю из включённого `genesis.bundle`:
`git clone genesis.bundle H:\dev\Genesis` (каталог назначения должен отсутствовать).
Если история не нужна, исходники из архива запускаются напрямую.
