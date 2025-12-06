# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个针对中国科学院大学(UCAS)在线慕课平台的自动化学习脚本，用于自动完成视频观看和PPT阅读任务。该项目使用 Selenium WebDriver 进行网页自动化操作。

## 常用命令

### 环境准备
```bash
# 安装依赖包
pip install -r requirements.txt

# 运行主脚本
python main.py
```

### 开发和测试
```bash
# 运行脚本（需要手动登录和配置URL）
python main.py

# 检查依赖
pip list
```

## 代码架构

### 核心模块结构
- `main.py` - 主脚本文件，包含完整的自动化流程
  - 视频播放和进度监控
  - PPT自动浏览
  - 章节进度扫描
  - 多UI版本适配（新版/旧版）

### 主要功能组件

1. **登录和导航**
   - 手动登录引导，支持扫码和账号密码登录
   - 自动保存课程主页URL用于后续导航

2. **进度扫描系统** (`scan_progress`)
   - 智能识别新旧版UI界面
   - 自动跳过已完成章节和测验
   - 返回未完成章节索引列表

3. **视频处理模块** (`process_single_chapter`)
   - 自动播放视频，支持倍速播放
   - 智能跳过已完成视频（剩余时间<5秒）
   - 进度条显示（使用tqdm）
   - 自动防暂停检测

4. **PPT处理模块**
   - 深度模拟阅读（50次滚动）
   - 强制滚动到底部触发完成状态
   - 增强鼠标移动兼容性

### 技术特性

- **多实例避免**: 单实例模式，只需登录一次
- **UI兼容性**: 自动检测和适配新版/旧版界面
- **智能跳过**: 自动识别已完成内容，提高效率
- **错误恢复**: 异常处理和自动重试机制
- **进度可视化**: 使用tqdm显示视频播放进度

## 依赖项

- `selenium` - 网页自动化框架
- `numpy` - 数值计算支持
- `pyautogui` - 鼠标和键盘控制
- `tqdm` - 进度条显示
- `pywin32` - Windows API支持（虽然项目已适配macOS）

## 使用注意事项

1. **首次使用**: 需要手动获取课程章节URL并更新到代码中
2. **浏览器要求**: 需要安装Chrome浏览器和对应的ChromeDriver
3. **平台支持**: 虽然代码适配了macOS，但也支持Windows平台
4. **登录方式**: 支持手机号登录和校内登录两种方式

## 配置说明

主要配置项在`main.py`的第305行：
```python
url = "http://mooc.mooc.ucas.edu.cn/mooc-ans/mycourse/studentstudy?chapterId=..."
```

需要用户根据实际课程页面URL更新此配置。