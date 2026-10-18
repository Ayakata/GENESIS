# Журнал проверенного прогресса

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
