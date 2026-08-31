# DAP Flash Tool

一个基于 CMSIS-DAP / pyOCD 的图形化下载工具原型，面向不同厂商 RAM 内核单片机的 Flash 算法差异场景。工具支持选择 CMSIS-Pack、外部 `.FLM` 算法文件、HEX/BIN/ELF 固件，并提供连接、擦除、下载、校验、复位运行等常用操作。

## 功能

- 自动枚举 CMSIS-DAP 调试器
- 建立持久化 CMSIS-Pack 库，Pack 首次添加时解析一次，后续启动直接读取缓存
- 支持同时保存多个 Pack，并按 Pack、芯片厂商和芯片系列分类筛选
- 支持按芯片型号关键词快速搜索
- 选择芯片后自动匹配 Pack 中的 Flash 算法；缺少算法时可手动添加并保存 `.FLM` 映射
- 选择 HEX、BIN、ELF、AXF 固件
- 自动记忆并恢复上次使用的芯片、固件、算法、地址、频率和下载选项
- 支持检测芯片、连接芯片、下载，以及下载时选择全片擦除、检验、复位运行（默认不全片擦除）
- 从当前 FLM 读取实际 Flash 起始地址/大小，并支持填写手动 FLM 使用的 RAM 起始地址/大小
- 解析 HEX 地址范围和入口地址
- HEX 校验时自动转换为临时二进制并执行 `compare`
- 日志面板实时显示 pyOCD 输出
- 日志面板只读，仍可选择和复制文本
- 日志按下载选项依次显示擦除、下载、检验、复位运行阶段

## 安装

```powershell
cd f:\_WORKSPACE\Python\program-tool
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 运行

```powershell
python -m dap_flash_tool
```

## 打包 EXE

```powershell
.\scripts\build_exe.ps1
```

生成文件位于：

```text
dist\DAPFlashTool\DAPFlashTool.exe
```

## 使用建议

1. 先点击“刷新探针”，确认 CMSIS-DAP 已被系统识别；调试器下拉框会显示 `UID | 探针名 | 目标`。
2. 从菜单栏“设置”添加或管理芯片包；可一次选择多个 `.pack` 文件，工具首次直接解析 PDSC 并持久化缓存。
3. DAP 频率默认 `10MHz`，可选 `1MHz`、`2MHz`、`4MHz`、`8MHz`、`10MHz`、`12MHz`、`16MHz`、`24MHz`。
4. 点击主界面的“选择芯片”打开选择窗口，可按厂商、系列和型号关键词筛选；双击芯片或点击“确认选择”后窗口自动关闭。
5. 选择芯片后会自动使用其所属 Pack 并在主界面显示匹配的算法；主界面的 “FLM Flash” 范围和 BIN 默认起始地址均从当前 FLM 文件读取，不使用芯片包 `<memory>` 范围。
6. 选择 HEX 固件后，工具只解析地址范围、大小和入口地址，不会根据固件名称或路径改变芯片选择。Pack 中没有算法时，可浏览选择 `.FLM`，该手动映射会随 Pack 缓存保存，并在连接和下载时覆盖目标启动 Flash 区域的算法。
7. 选择目标芯片和下载选项后点击“下载”；勾选全片擦除时会先独立擦除，手动 FLM 按其自身 Flash 范围擦除，其余情况使用 `pyocd erase --chip`，确认成功后才开始下载。下载完成后目标保持停止，勾选检验时执行 `compare`，HEX 会自动转为临时二进制再比较；只有勾选“复位运行”时才会在最后启动目标。
8. BIN 固件可下载，建议明确填写起始地址；工具不会使用芯片包中的 Flash 范围拦截下载，非标准 Flash 基址和容量由所选算法负责处理。ELF/AXF 固件包含自身加载地址，无需填写起始地址。ELF/AXF 检验会逐个比较文件中的加载段。
9. “算法 RAM”用于设置手动 FLM 运行所需的 RAM 起始地址和大小，默认是 `0x20000000 / 0x1000`，修改后会随其它设置一起保存。
10. 擦除、下载和检验默认使用复位下连接。检测到 SWD/JTAG 通信失败时会保持用户选择的 DAP 频率并停止流程，可手动降低频率或重新连接后重试。

## 说明

底层调用 pyOCD，因此可适配的芯片范围主要由 pyOCD 和 CMSIS-Pack 决定。pyOCD 可以通过 `--pack` 使用 `.pack` 文件或已解包目录中的 PDSC/FLM 描述；不同芯片厂商的 Pack 描述质量不一致，如果某个芯片无法自动识别，优先确认 Pack 是否包含正确的 PDSC、目标名和 FLM 算法。

旧版通用 Pack 如果只声明单个 Cortex 内核、但没有提供调试 AP 拓扑，手动算法模式会仅在连接层把该处理器兼容映射到 AP#0，避免 pyOCD 已发现内核后仍报 `No cores were discovered`。FLM 文件不会被修改，带有有效 AP 拓扑的芯片包也不会被覆盖。

上次使用记录保存在 `%APPDATA%\DAPFlashTool\settings.json`。

如果连接时提示 `Target type ... not recognized`，说明当前目标名没有被 pyOCD 内置目标或所选 Pack 识别。请确认已经添加正确的 `.pack` 文件，并在芯片选择窗口中选择 Pack 实际包含的目标名。
