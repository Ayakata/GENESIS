# Журнал проверенного прогресса

## 2026-10-18 — S01-4 принят

Единственный источник статуса — `GENESIS_ROADMAP.md`: **4/8** задач Sprint 01.
Коммит реализации: `3ff71755a53d108baf1506a21e6015a06240910b`.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| pytest, CPython 3.11.9/Windows | 146 passed in 9.60s | s01_evolution/evidence/verification/ |
| pytest, CPython 3.12.7/Windows | 146 passed in 9.47s | s01_evolution/evidence/verification/ |
| Ruff lint/format, mypy strict | успешно | s01_evolution/evidence/verification/ |
| Сборка wheel + sdist | успешно | s01_evolution/evidence/verification/ |
| Контроль/мутации × 3 seeds × 2 | 6/6 пар идентичны | s01_evolution/evidence/acceptance/ |
| Контроль без мутаций | точное наследование, variance=0 | acceptance/report.json |
| Мутационный режим | 570 локусов, bounded variation | acceptance/report.json |
| Максимальный совокупный остаток | 3.8198777474462986e-11 | acceptance/report.json |

Восемь генов влияют на механику через документированные компромиссы, но метрики
не участвуют в отборе. Во всех 12 процессах лимит популяции оставался неактивным,
а manifest фиксирует чистый implementation SHA. Регрессионные сценарии S01-1—S01-3
также прошли: 13 процессов среды и 12 процессов агентов.

Схемы config/state/artifact обновлены до v3. Ограничение популяции снижено до 250 000
из-за временных матриц движения; профиль памяти и скорости относится к S01-5.
Результат доказывает механику наследуемой вариативности, но не адаптацию и не
возникновение жизни. Следующее действие — S01-5, затем checkpoints/events в S01-6.

## 2026-10-18 — S01-3 принят

Единственный источник статуса — `GENESIS_ROADMAP.md`: **3/8** задач Sprint 01.
Коммит реализации: `f276f1aef44d74d50d5c174c0ba18a4692c3bb47`.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| pytest, CPython 3.11.9/Windows | 123 passed | s01_agents/evidence/verification/ |
| pytest, CPython 3.12.7/Windows | 123 passed in 8.95s | s01_agents/evidence/verification/ |
| Ruff lint/format, mypy strict | успешно | s01_agents/evidence/verification/ |
| Сборка wheel + sdist | успешно | s01_agents/evidence/verification/ |
| 3 seeds × closed/periodic × 2 повтора | 6/6 пар идентичны | s01_agents/evidence/acceptance/ |
| Максимальный совокупный остаток | 4.069988790433854e-11 | acceptance/report.json |

В 12 независимых процессах наблюдались 1442 рождения и 2762 смерти (сумма по
терминальным ledger всех повторов). Все manifest фиксируют чистый implementation SHA.
Проверяются локальная механика и отсутствие неучтённой энергии, но не эволюция.

Схемы config/state/artifact обновлены до v2. Исторические доказательства S01-1/S01-2
не переписывались. Environment-only сценарий адаптирован так, чтобы явно отключать
агентов, и повторно прошёл 13 процессов.

Ограничения: генов и мутаций ещё нет; сохранённый NPZ не возобновляется; готовый агент
остаётся временной моделью. Следующее действие — S01-4 (наследование, мутации,
компромиссы), затем профиль headless-цикла для S01-5. Блокера нет.

## 2026-10-18 — S01-1/S01-2 приняты

Единственный источник статуса — `GENESIS_ROADMAP.md`: **2/8** задач Sprint 01.
Коммит реализации: `c9860cafae543a7ac72932c72eb12fe00164715f`.
На момент контрольного эксперимента рабочее дерево было чистым; все manifests
фиксируют этот implementation commit. Следующий коммит добавляет только доказательства
и документацию прогресса; точный SHA виден в `git log`/вложенном bundle.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| Установка pinned зависимостей в пустой venv | успешно, CPython 3.12.14 | requirements-dev.lock.txt |
| Установка wheel, импорт вне дерева исходников | успешно, fingerprint совпадает | evidence/verification/wheel_smoke.json |
| pytest на установленном wheel | 97 passed in 2.18s | evidence/verification/pytest.txt |
| Ruff lint/format | успешно | evidence/verification/ruff.txt, format.txt |
| mypy strict | 20 source files, 0 errors | evidence/verification/mypy.txt |
| Сборка wheel + sdist | успешно | evidence/verification/build.txt |
| Архипелаг: 3 seeds × closed/periodic × 2 повтора | digest/метрики всех пар идентичны | evidence/acceptance/report.json |
| Контроль: source=0, decay=0, 500 тиков | остаток 0.0 | evidence/acceptance/closed_control/ |
| Максимальный абсолютный остаток баланса | 5.4569682106375694e-12 | evidence/acceptance/REPORT.md |

Все пути `evidence/...` в таблице относительны к `experiments/s01_environment/`.
Сценарий воспроизведения: `python experiments/s01_environment/reproduce.py --output runs/recheck`.
`runs/recheck` должен отсутствовать. Исходные YAML: `configs/archipelago.yaml`,
`configs/closed_system.yaml`; periodic-конфиг создаётся сценарием явно и сохраняется.

Научный вывод этой итерации: генератор и правила среды детерминированы в проверенном
бэкенде, перенос локален, источник и потери учтены. Результат ничего не говорит о
возникновении жизни или эволюции; соответствующие эксперименты пока не реализованы.

Пограничный дефект округления при d=0.25 устранён выпуклой формулой без clipping;
подробности и регрессионный импульс — ADR-0001 и `test_topology.py`.

Ограничения: Windows не проверен в этой среде; CI-матрица Ubuntu/Windows,
Python 3.11/3.12 добавлена, но внешний CI не запускался и remote не настроен.
Побитовая переносимость между платформами не обещается. Диск H: здесь недоступен.
Возобновление состояния/полные snapshots с RNG и событиями остаются S01-6.

Следующие 1–2 действия: реализовать S01-3 (SoA, движение/питание/репликация/смерть,
транзакционный учёт энергетических затрат), затем S01-4 (8 генов, наследование и мутации).
Блокера для продолжения работы с ядром нет; локальный Windows запуск требует переноса.
