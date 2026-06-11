# Component Patterns

## Dark Neo-Dashboard App Shell

Дата: 2026-06-10

Используется для рабочих экранов FoldersNUsersParser, где важны плотные таблицы, импорт, проверки и статусы.

Паттерн:

- Левый вертикальный Dock-sidebar с иконками `lucide-react`, активным пунктом и hover-увеличением через `motion`.
- Основной экран только в темной теме: layered navy/graphite background, cyan/electric-blue акценты, зеленый/оранжевый/красный для статусов.
- Панели и таблицы: полупрозрачные темные поверхности, тонкие cyan-border, мягкий glow, компактные controls.
- Таблицы аккаунтов: identity cell с аватаром, ником и username; номер с toggle hide/show; geo flag badge; validity badge с цветной точкой; icon-only action для проверки.
- Для визуального выбора допустимы встроенные theme variants, если они переключают только presentation layer и не меняют данные/API.
