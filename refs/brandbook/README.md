# refs/brandbook — фирменный стиль Rudstock

## Что здесь лежит в репозитории

- **`brand.json`** — машиночитаемые токены бренда. Единственный источник стиля для монтажа:
  `scripts/generate_comp.py` берёт из него цвета, шрифт и форму панелей, а `scripts/montage.py`
  записывает их в пульт нового прогона (`passport.colors/fonts/brand`).
- **`fonts/Inter-*.ttf`** — шрифт Inter (SIL Open Font License, текст лицензии в `fonts/OFL.txt`),
  начертания 400/500/600/700/800/900, подмножества latin + latin-ext + **cyrillic**.

## Что намеренно НЕ в репозитории

`brandbook.md`, `landing.md`, `canonical.md` — исходные документы брендбука. Они содержат
коммерческую стратегию (целевой AUM, порог входа, позиционирование, работа со СМИ), а этот
репозиторий публичный. Документы остаются локально и на сервере, в git не попадают
(см. правила в `.gitignore`).

Исходники на сервере (`ssh dmitry-direct`, хосты — `dmitryt` / `mrtsarkov`):

```
/home/mrtsarkov/app/brand_book/Брендбук Rudstock.md                     # версия 2.0, «Утверждено» — канон
/home/mrtsarkov/app/projects/t_brand_landing/BRAND_GUIDELINES.md        # дополнение по UI
/home/mrtsarkov/.gemini/antigravity/brain/e9808493-.../brand_book_2026_canonical.md
```

> **Внимание:** файл с именем `brand_book_2026_canonical.md` — **устаревшая** концепция
> (Cloud Dancer / Transformative Teal / Plum Noir / Playfair Display, 2026-04-03).
> Несмотря на слово «canonical» в имени, действующий стиль — «Architectural Monolith» v2.0
> (Inter, Alpha Red #EF3124, Bento). Устаревший документ скачан как `canonical.md` только для
> истории и в монтаже не используется.

## Как обновить токены

1. Забрать актуальные документы с сервера (пути выше).
2. Перенести изменения в `brand.json` — цвета, шрифты, форму.
3. Перегенерировать и пересобрать: `py -3 scripts\montage.py --label <метка> --take <дубль> --force comp`.
   Стадия `comp` потянет за собой рендер, сборку и приёмку.

## Как поставить шрифт заново (если папка `fonts/` пуста)

```powershell
$d = "refs\brandbook\fonts"
Invoke-WebRequest -Uri "https://gwfh.mranftl.com/api/fonts/inter?download=zip&subsets=latin,cyrillic,latin-ext&formats=ttf&variants=regular,500,600,700,800,900" -OutFile "$d\inter.zip"
Expand-Archive "$d\inter.zip" -DestinationPath $d -Force
```

Проверить, что кириллица на месте (иначе текст в кадре окажется пустым):

```powershell
py -3 scripts\measure_text.py   # или любой замер PIL по глифам А/Я/Ё
```
