#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
@Project ：Python 
@File    ：main.py
@IDE     ：PyCharm 
@Author  ：Cjx_1023
@Modifier：cchan & Gemini
@UpDateTime     ：2023/12/05
@Description: macOS 适配版本 - 单实例模式 (只登录一次) - 适配新版UI - 智能跳过已完成视频 - PPT深度阅读模式
'''
import numpy as np
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import pyautogui
import argparse

from tqdm import tqdm

# 解析视频持续时间
def convertTime(time_str):
    try:
        minutes, seconds = map(int, time_str.split(':'))
        total_time = minutes * 60 + seconds
        return total_time
    except Exception:
        return 0

# 移动鼠标函数 (适配 Mac)
def mouseMoveTo(element, driver):
    try:
        canvas_x_offset = driver.execute_script(
            "return window.screenX + (window.outerWidth - window.innerWidth) / 2 - window.scrollX;")
        canvas_y_offset = driver.execute_script(
            "return window.screenY + (window.outerHeight - window.innerHeight) - window.scrollY;")
        
        element_location = (element.rect["x"] + canvas_x_offset + element.rect["width"] / 2,
                            element.rect["y"] + canvas_y_offset + element.rect["height"] / 2)
        
        pyautogui.moveTo(element_location[0], element_location[1], duration=0.1)
    except Exception:
        pass

def is_finite_positive(value):
    try:
        return value is not None and np.isfinite(float(value)) and float(value) > 0
    except Exception:
        return False

def get_video_state(driver):
    """
    读取当前视频 iframe 内的播放状态。只读取状态，不触发播放。
    """
    state = {
        "current": 0,
        "duration": 0,
        "ended": False,
        "paused": True,
    }

    try:
        js_state = driver.execute_script("""
            const video = document.querySelector('video');
            if (!video) {
                return null;
            }
            return {
                current: Number.isFinite(video.currentTime) ? video.currentTime : 0,
                duration: Number.isFinite(video.duration) ? video.duration : 0,
                ended: !!video.ended,
                paused: !!video.paused
            };
        """)
        if js_state:
            state.update(js_state)
    except Exception:
        pass

    try:
        duration_ele = driver.find_element(By.CLASS_NAME, "vjs-duration-display")
        current_ele = driver.find_element(By.CLASS_NAME, "vjs-current-time-display")
        ui_duration = convertTime(duration_ele.text)
        ui_current = convertTime(current_ele.text)
        if ui_duration > 0:
            state["duration"] = ui_duration
        if ui_current > 0:
            state["current"] = ui_current
    except Exception:
        pass

    return state

def video_already_completed(driver):
    """
    在点击播放前判断视频是否已经完成。
    """
    state = get_video_state(driver)
    current = float(state.get("current") or 0)
    duration = float(state.get("duration") or 0)

    if state.get("ended"):
        return True, current, duration, "ended 状态"

    if is_finite_positive(duration):
        remaining = duration - current
        if current > 0 and remaining <= 5:
            return True, current, duration, f"剩余 {remaining:.1f}s"

    return False, current, duration, ""

def module_already_completed(driver, module_iframe):
    """
    在进入视频/PPT iframe 前，从外层任务点标记判断模块是否已完成。
    只检查 iframe 紧邻的任务容器，避免兄弟节点的完成状态干扰。
    """
    try:
        return bool(driver.execute_script("""
            let node = arguments[0];
            for (let i = 0; node && i < 4; i += 1, node = node.parentElement) {
                const className = String(node.className || '');
                if (/ans-job-finished|icon_Completed|jobFinish|job-finished/.test(className)) {
                    return true;
                }
                // 只检查直接子元素中的状态指示器，排除包含 iframe 的容器（避免兄弟节点干扰）
                for (let j = 0; j < node.children.length; j++) {
                    const child = node.children[j];
                    const childClass = String(child.className || '');
                    if (/ans-job-finished|icon_Completed|jobFinish|job-finished/.test(childClass)
                        && !child.querySelector('iframe')) {
                        return true;
                    }
                }
            }
            return false;
        """, module_iframe))
    except Exception:
        return False

# PPT iframe 选择器：覆盖 PDF、PPT、文档等多种类型
PPT_SELECTORS = (
    'iframe[src*="/ananas/modules/pdf/index.html"],'
    'iframe[src*="/ananas/modules/ppt/index.html"],'
    'iframe[src*="/ananas/modules/doc/index.html"]'
)

# 视频iframe选择器
VIDEO_SELECTORS = 'iframe[src*="/ananas/modules/video/index.html"]'

def locate_main_iframe(driver, timeout=20):
    """重新定位主内容 iframe，避免 StaleElementReferenceException。"""
    driver.switch_to.default_content()
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.ID, 'iframe'))
    )

def get_chapter_elements(driver):
    """
    获取当前页面的所有章节链接元素
    """
    # 尝试获取新版元素
    new_ui_elements = driver.find_elements(By.CSS_SELECTOR, ".posCatalog_select .posCatalog_name")
    if new_ui_elements:
        return new_ui_elements, True # True 表示新版 UI
    
    # 尝试获取旧版元素
    root_elements = driver.find_elements(By.CLASS_NAME, 'onetoone')
    if root_elements:
        a_elements = root_elements[0].find_elements(By.TAG_NAME, 'a')
        return a_elements, False # False 表示旧版 UI
    
    return [], False

def scan_progress(driver):
    """
    扫描当前课程页面的进度，返回未完成章节的索引列表
    """
    print("正在扫描章节进度...")
    
    try:
        # 等待页面加载
        WebDriverWait(driver, 15).until(lambda d: d.find_elements(By.CLASS_NAME, 'onetoone') or d.find_elements(By.CLASS_NAME, 'posCatalog_select'))
    except TimeoutException:
        print("扫描超时：未找到章节列表，请确认已进入课程章节页面。")
        return []

    elements, is_new_ui = get_chapter_elements(driver)
    print(f"识别到 {len(elements)} 个章节 (UI模式: {'新版' if is_new_ui else '旧版'})")
    
    ret = []
    print("-----------------------未完成章节列表---------------------")
    
    if is_new_ui:
        for i, el in enumerate(elements):
            try:
                # 获取父级 div.posCatalog_select 以检查完成状态
                row_div = el.find_element(By.XPATH, "./..")
                row_text = row_div.text
                completed_icon = row_div.find_elements(By.CLASS_NAME, "icon_Completed")
                
                # 如果没有 icon_Completed 且文本不包含“已完成”
                if not completed_icon and "已完成" not in row_text:
                    if "测验" not in row_text and "Quiz" not in row_text:
                        ret.append(i)
            except:
                pass
    else:
        # 旧版逻辑
        try:
            span_elements = driver.find_elements(By.CLASS_NAME, 'roundpointStudent')
            min_len = min(len(span_elements), len(elements))
            for i in range(min_len):
                class_attr = span_elements[i].get_attribute('class')
                if 'orange01' in class_attr: # 黄色表示未完成
                    spans = elements[i].find_elements(By.TAG_NAME, "span")
                    is_quiz = False
                    for span in spans:
                        if "quiz" in span.text.lower() or "测验" in span.text:
                            is_quiz = True
                            break
                    if not is_quiz:
                        ret.append(i)
        except Exception as e:
            print(f"旧版扫描出错: {e}")

    print("未完成章节索引：", ret)
    return ret

def process_single_chapter(driver, chapter_index, force=False):
    """
    处理单个章节：包含视频播放和PPT查看
    :param driver: WebDriver 实例
    :param chapter_index: 章节索引
    :param force: 是否强制播放（即使无法获取时长）
    """
    print(f"\n>>> 开始处理第 {chapter_index} 个章节...")
    
    # 1. 重新获取元素 (防止页面刷新后元素失效)
    elements, _ = get_chapter_elements(driver)
    if chapter_index >= len(elements):
        print("索引越界，跳过")
        return

    target_chapter = elements[chapter_index]
    
    # 2. 点击进入章节
    try:
        driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", target_chapter)
        time.sleep(1)
        # 尝试常规点击，失败则使用 JS 点击
        try:
            target_chapter.click()
        except:
            driver.execute_script("arguments[0].click();", target_chapter)
    except Exception as e:
        print(f"点击章节失败: {e}")
        return

    time.sleep(5) # 等待内容加载

    # 3. 切换到主 iframe
    try:
        iframe1 = locate_main_iframe(driver)
        driver.switch_to.frame(iframe1)
    except TimeoutException:
        print("未找到内容 iframe，可能该章节为空或加载失败。")
        return

    # ---------------- 视频处理 ----------------
    try:
        # 查找所有视频 iframe
        video_frames = driver.find_elements(By.CSS_SELECTOR, VIDEO_SELECTORS)
        total_videos = len(video_frames)
        print(f"  - 检测到视频数量: {total_videos}")

        processed = 0
        while processed < total_videos:
            try:
                # 重新定位 iframe 和视频帧列表
                driver.switch_to.default_content()
                iframe1 = locate_main_iframe(driver)
                driver.switch_to.frame(iframe1)
                video_frames = driver.find_elements(By.CSS_SELECTOR, VIDEO_SELECTORS)

                if processed >= len(video_frames):
                    print(f"    [警告] DOM 中剩余视频帧({len(video_frames)})少于预期(已处理 {processed}, 总计 {total_videos})")
                    break

                current_frame = video_frames[processed]

                # 在进入 iframe 前检测任务点是否已完成
                if module_already_completed(driver, current_frame):
                    print(f"    [跳过] 视频 {processed+1}/{total_videos} 任务点已标记完成，无需播放。")
                    processed += 1
                    continue

                driver.switch_to.frame(current_frame)

                # 播放逻辑
                print(f"    正在处理视频 {processed+1}/{total_videos}...")

                try:
                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "video")))
                except TimeoutException:
                    pass

                completed, pre_current, pre_duration, reason = video_already_completed(driver)
                if completed:
                    print(f"    [跳过] 视频 {processed+1}/{total_videos} 已播放完毕（当前: {pre_current:.1f}s / 总时长: {pre_duration:.1f}s，{reason}）。")
                    processed += 1
                    continue

                start_btn = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "vjs-big-play-button")))
                driver.execute_script("arguments[0].click();", start_btn)
                print("    已点击播放按钮，等待视频加载...")
                time.sleep(3)  # 增加等待时间，确保视频开始播放

                # 静音处理
                try:
                    print("    正在设置静音...")
                    # 尝试多种方式设置静音
                    # 方式1: 通过音量按钮
                    try:
                        volume_btn = driver.find_element(By.CLASS_NAME, "vjs-mute-control")
                        if "vjs-vol-0" not in volume_btn.get_attribute("class"):
                            volume_btn.click()
                            print("    已通过音量按钮设置静音")
                    except:
                        pass

                    # 方式2: 通过 JavaScript 直接设置视频元素静音
                    try:
                        video_element = driver.find_element(By.TAG_NAME, "video")
                        driver.execute_script("arguments[0].muted = true;", video_element)
                        driver.execute_script("arguments[0].volume = 0;", video_element)
                        print("    已通过 JavaScript 设置静音")
                    except:
                        pass
                except Exception as e:
                    print(f"    静音设置失败（继续播放）: {e}")

                # 获取时长和当前进度
                duration_ele = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "vjs-duration-display")))
                current_ele = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "vjs-current-time-display")))

                # 等待视频真正开始播放（时间开始变化）
                print("    等待视频开始播放...")
                initial_time = convertTime(current_ele.text)
                wait_count = 0
                while wait_count < 10:  # 最多等待10秒
                    time.sleep(1)
                    current_check = convertTime(current_ele.text)
                    if current_check > initial_time or current_check > 0:
                        print(f"    视频已开始播放 (当前时间: {current_check}s)")
                        break
                    wait_count += 1

                total_time = convertTime(duration_ele.text)
                current_time_val = convertTime(current_ele.text)

                print(f"    [调试] 视频总时长: {total_time}s, 当前时间: {current_time_val}s")

                # 如果总时长为0，尝试通过 JavaScript 获取视频时长
                if total_time == 0:
                    print("    视频时长未加载，尝试通过 JavaScript 获取...")
                    try:
                        video_element = driver.find_element(By.TAG_NAME, "video")
                        js_duration = driver.execute_script("return arguments[0].duration;", video_element)
                        if js_duration and js_duration > 0:
                            total_time = int(js_duration)
                            print(f"    通过 JavaScript 获取到时长: {total_time}s")
                    except:
                        pass

                # 如果总时长为0，说明可能还没加载完成，等待一下
                if total_time == 0:
                    print("    视频时长未加载，等待中...")
                    for _ in range(5):
                        time.sleep(1)
                        total_time = convertTime(duration_ele.text)
                        if total_time > 0:
                            break
                        # 再次尝试 JavaScript 获取
                        try:
                            video_element = driver.find_element(By.TAG_NAME, "video")
                            js_duration = driver.execute_script("return arguments[0].duration;", video_element)
                            if js_duration and js_duration > 0:
                                total_time = int(js_duration)
                                break
                        except:
                            pass

                # 如果仍然无法获取时长，根据 force 参数决定是否继续
                if total_time == 0:
                    if force:
                        print(f"    [强制模式] 无法获取视频时长，将使用智能检测方式继续播放...")
                        # 使用智能检测方式：通过检测视频播放状态来判断
                        total_time = 0  # 标记为未知时长
                    else:
                        print(f"    [警告] 无法获取视频时长，跳过此视频")
                        print(f"    提示: 使用 --force 参数可以强制播放")
                        processed += 1
                        continue

                # 如果总时长为0（强制模式），使用智能检测
                if total_time == 0:
                    print(f"    开始播放视频 (强制模式：时长未知，将智能检测完成状态)")

                    # 倍速设置 (尝试)
                    try:
                        speed_btn = driver.find_element(By.CLASS_NAME, "vjs-playback-rate")
                        speed_btn.click()
                        time.sleep(0.5)
                        speed_btn.click() # 切换到 2x
                        print("    已设置倍速播放")
                    except:
                        print("    无法设置倍速（可能不支持）")

                    # 强制模式：通过检测视频播放状态来判断是否完成
                    last_time = current_time_val
                    consecutive_paused_count = 0
                    max_no_progress = 30  # 如果30秒没有进度，认为视频已完成
                    no_progress_count = 0

                    print("    正在播放（强制模式）...")
                    while True:
                        try:
                            curr_time = last_time
                            video_playing = True

                            # 优先使用 JavaScript 获取视频状态（更准确）
                            try:
                                video_element = driver.find_element(By.TAG_NAME, "video")
                                js_current = driver.execute_script("return arguments[0].currentTime;", video_element)
                                js_duration = driver.execute_script("return arguments[0].duration;", video_element)
                                js_paused = driver.execute_script("return arguments[0].paused;", video_element)
                                js_ended = driver.execute_script("return arguments[0].ended;", video_element)

                                if js_ended:
                                    print("\n    视频播放完成（检测到 ended 状态）。")
                                    break

                                if js_duration > 0 and js_current >= js_duration - 2:
                                    print(f"\n    视频播放完成（当前: {js_current:.1f}s / 总时长: {js_duration:.1f}s）。")
                                    break

                                if js_current is not None and js_current >= 0:
                                    curr_time = int(js_current)

                                video_playing = not js_paused

                            except:
                                # 回退到页面元素
                                try:
                                    curr_time = convertTime(current_ele.text)
                                except:
                                    pass

                            # 检查视频是否在播放（时间是否在增加）
                            if curr_time > last_time:
                                no_progress_count = 0
                                last_time = curr_time
                                print(f"    播放中... {curr_time}s", end='\r')
                            else:
                                no_progress_count += 1

                            # 检测暂停状态（只在真正检测到暂停时才处理）
                            if not video_playing:
                                consecutive_paused_count += 1
                                # 只有在连续检测到暂停超过3秒时才尝试恢复
                                if consecutive_paused_count == 3:
                                    try:
                                        play_control = driver.find_element(By.CLASS_NAME, "vjs-play-control")
                                        if "vjs-paused" in play_control.get_attribute("class"):
                                            play_control.click()
                                            print("\n    检测到暂停，已恢复播放")
                                    except:
                                        pass
                                    consecutive_paused_count = 0
                            else:
                                consecutive_paused_count = 0

                            # 如果30秒没有进度，可能视频已完成
                            if no_progress_count >= max_no_progress:
                                print(f"\n    检测到长时间无进度，可能视频已完成。")
                                break

                            time.sleep(1)

                        except Exception as e:
                            # 静默处理错误
                            time.sleep(1)

                    print("    视频处理完成。")
                    processed += 1
                    continue

                # 正常模式：有明确的时长
                # 如果剩余时间少于 5 秒，则跳过（但确保不是刚播放就判断）
                remaining_time = total_time - current_time_val
                if remaining_time < 5 and current_time_val > 10:  # 只有当已经播放超过10秒且剩余少于5秒时才跳过
                    print(f"    [跳过] 视频 {processed+1}/{total_videos} 已完成 ({current_time_val}s / {total_time}s，剩余 {remaining_time}s)。")
                    processed += 1
                    continue

                print(f"    开始播放视频 (总时长: {total_time}s, 当前: {current_time_val}s, 剩余: {remaining_time}s)")

                # 倍速设置 (尝试)
                try:
                    speed_btn = driver.find_element(By.CLASS_NAME, "vjs-playback-rate")
                    speed_btn.click()
                    time.sleep(0.5)
                    speed_btn.click() # 切换到 2x
                    print("    已设置倍速播放")
                except:
                    print("    无法设置倍速（可能不支持）")

                # 循环检测直到结束，使用 tqdm 显示进度条
                with tqdm(total=total_time, desc=f"    视频 {processed+1}/{total_videos}", unit="s", leave=True, ncols=80) as pbar:
                    # 初始化进度条到当前位置
                    if current_time_val > 0:
                        pbar.update(current_time_val)

                    last_time = current_time_val
                    consecutive_paused_count = 0  # 连续检测到暂停的次数

                    while True:
                        try:
                            # 优先使用 JavaScript 获取视频时间（更准确可靠）
                            curr_time = current_time_val
                            video_playing = True

                            try:
                                video_element = driver.find_element(By.TAG_NAME, "video")
                                js_current = driver.execute_script("return arguments[0].currentTime;", video_element)
                                js_paused = driver.execute_script("return arguments[0].paused;", video_element)
                                js_ended = driver.execute_script("return arguments[0].ended;", video_element)

                                if js_ended:
                                    pbar.n = total_time
                                    pbar.refresh()
                                    print("\n    视频播放完成（检测到 ended 状态）。")
                                    break

                                # 使用 JavaScript 获取的时间（更准确）
                                if js_current is not None and js_current >= 0:
                                    curr_time = int(js_current)

                                video_playing = not js_paused

                            except Exception as js_error:
                                # 如果 JavaScript 获取失败，回退到页面元素
                                try:
                                    curr_time = convertTime(current_ele.text)
                                except:
                                    curr_time = last_time

                            # 更新进度条（使用更准确的时间）
                            if curr_time > pbar.n:
                                pbar.update(curr_time - pbar.n)

                            # 检查是否播放完成（剩余时间少于3秒）
                            remaining = total_time - curr_time
                            if remaining < 3 and remaining >= 0:
                                pbar.n = total_time
                                pbar.refresh()
                                print("\n    视频播放完成。")
                                break

                            # 检测暂停状态（只在真正检测到暂停时才处理）
                            if not video_playing:
                                consecutive_paused_count += 1
                                # 只有在连续检测到暂停超过3秒时才尝试恢复
                                if consecutive_paused_count == 3:
                                    try:
                                        play_control = driver.find_element(By.CLASS_NAME, "vjs-play-control")
                                        if "vjs-paused" in play_control.get_attribute("class"):
                                            play_control.click()
                                            print("\n    检测到暂停，已恢复播放")
                                    except:
                                        pass
                            else:
                                consecutive_paused_count = 0
                                last_time = curr_time

                            time.sleep(1)

                        except Exception as e:
                            # 静默处理错误，避免频繁打印
                            time.sleep(1)

                print(f"    视频 {processed+1}/{total_videos} 处理完成。")
                processed += 1

            except StaleElementReferenceException:
                print(f"    [重试] 视频 {processed+1}/{total_videos} 帧引用过期，重新定位...")
                time.sleep(1)
                continue
            except Exception as e:
                print(f"    视频 {processed+1}/{total_videos} 处理出错: {e}")
                import traceback
                traceback.print_exc()
                processed += 1  # 前进计数器，避免死循环

    except Exception as e:
        print(f"  视频模块出错: {e}")

    # ---------------- PPT 处理 ----------------
    try:
        driver.switch_to.default_content()
        iframe1 = locate_main_iframe(driver)
        driver.switch_to.frame(iframe1)
        ppt_frames = driver.find_elements(By.CSS_SELECTOR, PPT_SELECTORS)
        total_ppts = len(ppt_frames)
        if total_ppts > 0:
            print(f"  - 检测到 PPT/文档数量: {total_ppts}")

        processed = 0
        while processed < total_ppts:
            try:
                # 重新定位 iframe 和 PPT 帧列表
                driver.switch_to.default_content()
                iframe1 = locate_main_iframe(driver)
                driver.switch_to.frame(iframe1)
                ppt_frames = driver.find_elements(By.CSS_SELECTOR, PPT_SELECTORS)

                if processed >= len(ppt_frames):
                    print(f"    [警告] DOM 中剩余 PPT 帧({len(ppt_frames)})少于预期(已处理 {processed}, 总计 {total_ppts})")
                    break

                current_frame = ppt_frames[processed]

                # 在进入 iframe 前检测任务点是否已完成
                if module_already_completed(driver, current_frame):
                    print(f"    [跳过] PPT {processed+1}/{total_ppts} 任务点已标记完成，无需阅读。")
                    processed += 1
                    continue

                driver.switch_to.frame(current_frame)

                print(f"    正在处理 PPT {processed+1}/{total_ppts}...")

                # 1. 查找并点击 PPT 查看器自带的全屏按钮
                fullscreen_clicked = False
                fullscreen_selectors = [
                    'div.fullsrceen',
                    'span.fullsrceenIcon',
                    'button[title="全屏"]',
                    'span[title="全屏"]',
                    'div[title="全屏"]',
                    'a[title="全屏"]',
                    '[class*="fullscreen"]',
                    '[class*="FullScreen"]',
                    '[class*="full-screen"]',
                    '.bpFullScreen',
                    '#fullscreen',
                    '[data-action="fullscreen"]',
                ]
                for selector in fullscreen_selectors:
                    try:
                        fs_btn = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        fs_btn.click()
                        fullscreen_clicked = True
                        print(f"    已点击 PPT 全屏按钮 ({selector})")
                        time.sleep(2)
                        break
                    except (TimeoutException, NoSuchElementException):
                        continue

                if not fullscreen_clicked:
                    print("    未找到 PPT 全屏按钮，继续常规阅读")

                # 2. 进入嵌套 iframe #panView，逐步滚动 PPT
                try:
                    panview = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, 'panView'))
                    )
                    driver.switch_to.frame(panview)
                    print("    已进入 #panView iframe")

                    # 获取页数和总高度
                    page_count = driver.execute_script(
                        "return document.querySelectorAll('.pageNum').length;"
                    )
                    scroll_height = driver.execute_script(
                        "return document.documentElement.scrollHeight;"
                    )
                    client_height = driver.execute_script(
                        "return document.documentElement.clientHeight;"
                    )

                    print(f"    PPT 共 {page_count} 页，总高度 {scroll_height}px，可视高度 {client_height}px")

                    if scroll_height <= client_height:
                        print("    PPT 无需滚动（内容未超出视口）")
                    else:
                        print("    开始逐步滚动...")
                        # 每次滚动一页的高度，模拟真实阅读
                        step_height = client_height * 1.5
                        total_steps = int((scroll_height - client_height) / step_height) + 1

                        for i in range(total_steps):
                            driver.execute_script(
                                "document.documentElement.scrollTop += arguments[0];",
                                step_height
                            )
                            time.sleep(0.5)

                        # 确保滚到底部
                        driver.execute_script(
                            "document.documentElement.scrollTop = document.documentElement.scrollHeight;"
                        )
                        print("    已滚动到底部")

                except TimeoutException:
                    print("    未找到 #panView iframe，跳过 PPT 滚动")
                except Exception as e:
                    print(f"    PPT 滚动出错: {e}")

                # 3. 停留等待完成记录
                print("    已触底，停留 3 秒以确认完成...")
                time.sleep(3)

                # 4. 退出全屏
                if fullscreen_clicked:
                    try:
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                        time.sleep(1)
                    except:
                        pass

                print(f"    PPT {processed+1}/{total_ppts} 处理完毕。")
                processed += 1

            except StaleElementReferenceException:
                print(f"    [重试] PPT {processed+1}/{total_ppts} 帧引用过期，重新定位...")
                time.sleep(1)
                continue
            except Exception as e:
                print(f"    PPT {processed+1}/{total_ppts} 处理出错: {e}")
                import traceback
                traceback.print_exc()
                processed += 1  # 前进计数器，避免死循环

    except Exception as e:
        print(f"  PPT模块出错: {e}")

    # 4. 退出 iframe，准备返回
    driver.switch_to.default_content()

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='超星慕课刷课脚本')
    parser.add_argument('-url', '--url', type=str, required=True,
                        help='课程章节页面的URL')
    parser.add_argument('--force', action='store_true',
                        help='强制播放模式：即使无法获取视频时长也继续播放')
    args = parser.parse_args()
    
    print("="*60)
    print("   超星慕课刷课脚本 (Mac 单实例版)")
    print("   特点：只登录一次，自动顺序刷课，无需重复扫码。")
    print("="*60 + "\n")

    # 1. 启动浏览器 (只做一次)
    driver = webdriver.Chrome()
    driver.maximize_window()
    
    # 2. 手动登录引导
    url = args.url
    try:
        driver.get(url)
        print("\n>>> 浏览器已打开。")
        print(">>> 请手动扫码登录，并【进入具体的课程章节列表页面】。")
        print(">>> (确保能看到左侧的章节目录)")
        input(">>> 准备就绪后，请按回车键 (Enter) 开始全自动刷课...")
    except Exception as e:
        print(f"浏览器启动失败: {e}")
        return

    # 3. 记录课程主页 URL，方便后续返回
    course_list_url = driver.current_url
    print(f"已锁定课程主页: {course_list_url}")

    while True:
        # 4. 扫描进度
        # 每次循环都扫描一次，确保状态最新
        unfinished_indices = scan_progress(driver)
        
        if not unfinished_indices:
            print("\n恭喜！所有章节已显示完成 (或未检测到未完成章节)。")
            break
            
        print(f"\n本轮待处理章节数: {len(unfinished_indices)}")
        
        # 5. 顺序处理
        for idx in unfinished_indices:
            try:
                # 确保在列表页
                if driver.current_url != course_list_url:
                    driver.get(course_list_url)
                    time.sleep(3)
                
                process_single_chapter(driver, idx, force=args.force)
                
                # 处理完一个章节，强制回到列表页，为下一个做准备
                print("  < 返回目录页...")
                driver.get(course_list_url)
                time.sleep(3) # 等待列表刷新
                
            except Exception as e:
                print(f"处理过程中发生异常: {e}")
                # 尝试恢复到目录页
                try:
                    driver.get(course_list_url)
                    time.sleep(5)
                except:
                    break
        
        # 询问是否再次扫描 (防止有漏网之鱼)
        print("\n一轮循环结束，准备重新扫描状态...")
        time.sleep(2)

    print("脚本运行结束。")
    driver.quit()

if __name__ == "__main__":
    main()
