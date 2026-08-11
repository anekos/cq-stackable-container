# stackable-container

スタッキング（積み重ね）できる箱を CadQuery で生成するパラメトリックモデル。

リファレンスとして同梱している `sample.stl` の形状を計測し、それを高さ・縦横・厚みの
4 パラメータで再現できるようにしたもの。

## 使い方

```console
$ uv run stackable-container build            # dist/ に STL を出力
$ uv run stackable-container build out.stl    # 出力先を指定
$ uv run stackable-container build --show     # ビューアで確認
$ make watch                                  # ソース変更を監視してビルド＆表示
```

パラメータは `--width` などのオプションで指定する（`Param` から自動生成される）。

## パラメータ

| 名前 | 既定値 | 意味 |
| --- | --- | --- |
| `width` | 120 | 外寸 X |
| `depth` | 120 | 外寸 Y |
| `height` | 80 | 外寸 Z（底面から天面リムまで） |
| `thickness` | 2.0 | 壁厚・床厚 |

既定値は `sample.stl` と同じ。それ以外の寸法は壁厚 `t` に対する比としてモジュール定数に
まとめてあり、パラメータを増やさずに全体のバランスが保たれるようにしている。

| 定数 | 値 | t=2 のとき | 意味 |
| --- | --- | --- | --- |
| `CORNER_RADIUS_RATIO` | 2.0 | R4.0 | 垂直な四隅の丸み |
| `BOTTOM_RADIUS_RATIO` | 0.5 | R1.0 | 底面まわりのフィレット |
| `CLEARANCE_RATIO` | 0.2 | 0.4 | 脚と、下段の内壁とのすき間 |
| `BLEND_RADIUS_RATIO` | 1.5 | R3.0 | 段差を構成する円弧の半径 |
| `LIP_HEIGHT` | 11.0 | 11.0 | 底面から段差の中心までの高さ |
| `BLEND_STEPS` | 8 | — | 段差の円弧 1 本あたりの loft 断面数 |

## 形状

Z の原点は底面。上部の「本体」と、下段の口に落ち込む「脚（フット）」があり、その間を
S 字の段差でつないでいる。

```
   z=80 ┬  ┌─┐                            ┌─┐   ← 天面リム（幅 t）
        │  │ │                            │ │
        │  │ │  ← 外壁 x=±60              │ │   ← 内壁 x=±58（壁厚 t）
        │  │ │                            │ │
 z=13.4 ┤  │ └╮                          ╭┘ │   ← 上の円弧（R3, 壁から離れ始める）
   z=11 ┤   ╲ ╲     段差の中心            ╱ ╱
  z=8.6 ┤    ╰─┐                        ┌─╯     ← 下の円弧（R3, 脚の壁に接する）
        │      │  ← 脚 x=±57.6           │
    z=2 ┤      │  ┌──────────────────────┘      ← 床の上面（床厚 t）
    z=1 ┤      ╰╮                       ╭╯      ← 底面フィレット（R1）
    z=0 ┴       └───────────────────────┘
```

段差は**半径の等しい 2 つの円弧が接する S 字**。上の円弧は本体の外壁に、下の円弧は脚の
外壁にそれぞれ接するので、上下どちらにも角が立たない。

- 内側への後退量 `inset = t + clearance`（t=2 で 2.4）
- 円弧の中心角 `θ = acos(1 - inset / 2 / blend)`（t=2 で 53.13°）
- S 字の高さ `2 * blend * sin(θ)`（t=2 で 4.8）

`inset` が本体の内寸（片側 t）よりクリアランス分だけ大きいので、脚は下段の口に
`clearance` のすき間で収まる。

## コードの構成

`src/stackable_container/main.py` が本体。`Param`（pydantic モデル）と、副作用のない
`build(param) -> cq.Workplane` だけを持ち、CLI 側の `__init__.py` が
`click_cadquery.define_options` でオプションを自動生成して呼び出す。

### `_section(width, depth, radius)`

四隅を丸めた長方形を `cq.Sketch` で返すヘルパー。すべての水平断面はこれ。

```python
cq.Sketch().rect(width, depth).vertices().fillet(radius)
```

3D の `edges("|Z").fillet()` ではなく最初から丸めた断面を使うことで、後段の loft と
シェルが素直に通る。

### `_at(sketch, z)` / `_prism(section, z0, z1)`

`_at` はスケッチを Z 方向に移動するだけ。`_prism` はそれを `placeSketch().extrude()` で
`z0`〜`z1` の柱にする。脚と本体のストレート部分に使う。

### `_step_profile(inset, blend)`

S 字を「内側への後退量, 段差中心からの相対 Z」の列として返す。

上の円弧は角度 `a` を 0→θ と振って `(blend * (1 - cos a), half - blend * sin a)`。
下の円弧は上の円弧を点対称にコピーしたもの（`(inset - d, -z)` を逆順）で、接点が重複
しないよう先頭を落として連結する。

円弧そのものを CadQuery に描かせるのではなく、この列から断面を作って loft する方式に
している。垂直な壁と違って四隅では S 字が回り込むため、断面列で近似するのが一番素直な
ため。

### `build(param)`

1. `_step_profile` から S 字の断面列を作り、`placeSketch(*sketches).loft(ruled=False)` で
   段差のソリッドを作る。断面はすべて角 R が同じ丸め長方形で、大きさだけが変わる。
2. 脚の柱（`0`〜`step_bottom`）と本体の柱（`step_top`〜`height`）を union して外形が完成。
3. `faces("<Z").edges().fillet(t * BOTTOM_RADIUS_RATIO)` で底面まわりを丸める。
4. `faces(">Z").shell(-t)` で天面を開口して内側に肉抜き。

内面は**シェルのオフセットとして自動的に出る**のがポイントで、S 字の内側は
`blend - t`（上）と `blend + t`（下）の半径になり、床は底面フィレットに関係なく
`z = t` で平らになる。内面を明示的に作る必要はない。

なお底面フィレット（R1）は壁厚（2）より小さいが、OCCT がシェル時に内側の角を
シャープに落として処理するため問題ない。

## sample.stl との一致度

| 項目 | sample.stl | 生成物 |
| --- | --- | --- |
| 体積 | 99588.4 | 99594.4（差 0.006%） |
| 外形 / 内壁 / 脚 / 床 / 天面の各基準面 | — | すべて一致 |
| 断面外寸 s(z) | — | 全高にわたり 0.007 mm 以内 |
| 頂点間の最大偏差 | — | 0.66 mm（平均 0.045 mm） |

唯一ずれるのは**段差部分の四隅**。`sample.stl` は転がり球による 3D ブレンドで処理されて
いるのに対し、こちらは S 字断面を輪郭に沿って掃引しているため、高さ 4.8 mm の帯の隅だけ
最大 0.66 mm 異なる。壁面・脚・嵌合部は完全に一致するので、積み重ねの勘合には影響しない。

## 開発

```console
$ uv run ruff check src
$ uv run ruff format src
$ uv run mypy src
$ uv run pytest
```

`pre-commit` で mypy / ruff が走る。
