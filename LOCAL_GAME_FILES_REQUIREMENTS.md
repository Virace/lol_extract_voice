# 本地完整测试所需游戏文件清单

> 说明：当前项目很多功能依赖真实《英雄联盟》客户端资源。  
> 若仅运行纯单元测试（当前 `tests/`），不需要这些实体文件；若要执行完整功能验证（更新/哈希/解包/事件映射），请准备下列路径。

## 路径基准

- `GAME_PATH`：你在 `.lol.env` 中配置的游戏根目录
- `REGION`：例如 `zh_CN`、`en_US`、`ko_KR`

## 文件清单（相对 `GAME_PATH`）

| 类别 | 路径/模式 | 必需程度 | 作用模块 | 备注 |
|---|---|---|---|---|
| 版本元数据 | `Game/content-metadata.json` | 必需 | `data.manifest`、`hashes.manager` | 用于读取游戏版本号（如 `15.14`）。 |
| 英雄 WAD | `Game/DATA/FINAL/Champions/*.wad.client` | 必需（英雄相关功能） | `main.py`、`hashes.manager` | 提取英雄皮肤 BIN、音频 BNK/WPK。 |
| 地图 WAD | `Game/DATA/FINAL/Maps/Shipping/*.wad.client` | 必需（地图相关功能） | `main.py`、`hashes.manager` | 提取地图 BIN、音频资源。 |
| LCU 默认资源包 | `LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad` | 必需（数据更新、LCU 音频） | `data.manifest`、`main.py(get_lcu_audio)` | `default-assets.wad` 或 `default-assets*.wad`。 |
| LCU 语言资源包 | `LeagueClient/Plugins/rcp-be-lol-game-data/{REGION}-assets.wad` | 必需（多语言更新/语音） | `data.manifest`、`main.py(get_lcu_audio)` | 若 `REGION=en_US`，逻辑上会回退到 `default` 资源。 |
| 游戏可执行文件 | `Game/League of Legends.exe` | 可选（校验用途） | `hashes.manager` | 仅用于 `remote` 模式路径有效性检查。 |

## 功能到文件依赖映射

| 功能 | 最少需要文件 |
|---|---|
| 更新游戏数据（`GameDataUpdater.check_and_update`） | `content-metadata.json` + `default-assets*.wad` + `{REGION}-assets.wad` |
| 生成 BIN/BNK 哈希（`HashManager.get_bin_hashes/get_bnk_hashes`） | `content-metadata.json` + `Champions/*.wad.client` + `Maps/Shipping/*.wad.client` |
| 提取游戏音频（`get_game_audio`） | 上述哈希依赖 + 对应英雄/地图 WAD |
| 提取 LCU 选禁语音（`get_lcu_audio`） | `default-assets.wad` + `{REGION}-assets.wad` |

## 建议的本地预检命令（WSL）

```bash
# 假设已在 .lol.env 配置 LOL_GAME_PATH
test -f "$LOL_GAME_PATH/Game/content-metadata.json" && echo "ok: content-metadata.json"
ls "$LOL_GAME_PATH/Game/DATA/FINAL/Champions/"*.wad.client >/dev/null 2>&1 && echo "ok: champion wads"
ls "$LOL_GAME_PATH/Game/DATA/FINAL/Maps/Shipping/"*.wad.client >/dev/null 2>&1 && echo "ok: map wads"
ls "$LOL_GAME_PATH/LeagueClient/Plugins/rcp-be-lol-game-data/default-assets"*.wad >/dev/null 2>&1 && echo "ok: default assets"
test -f "$LOL_GAME_PATH/LeagueClient/Plugins/rcp-be-lol-game-data/${LOL_GAME_REGION}-assets.wad" && echo "ok: region assets"
```
