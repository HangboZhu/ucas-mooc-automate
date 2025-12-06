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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import pyautogui

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

def process_single_chapter(driver, chapter_index):
    """
    处理单个章节：包含视频播放和PPT查看
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
        iframe1 = WebDriverWait(driver, 20).until(
            EC.visibility_of_element_located((By.ID, 'iframe'))
        )
        driver.switch_to.frame(iframe1)
    except TimeoutException:
        print("未找到内容 iframe，可能该章节为空或加载失败。")
        return

    # ---------------- 视频处理 ----------------
    try:
        # 查找所有视频 iframe
        video_frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="/ananas/modules/video/index.html"]')
        print(f"  - 检测到视频数量: {len(video_frames)}")
        
        for v_idx, _ in enumerate(video_frames):
            # 必须重新定位 iframe，因为 switch_to 可能会导致引用丢失
            driver.switch_to.default_content()
            driver.switch_to.frame(iframe1)
            video_frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="/ananas/modules/video/index.html"]')
            driver.switch_to.frame(video_frames[v_idx])
            
            # 播放逻辑
            try:
                start_btn = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "vjs-big-play-button")))
                driver.execute_script("arguments[0].click();", start_btn)
                time.sleep(2)
                
                # --- 修改：智能跳过已完成视频 ---
                # 获取时长和当前进度
                duration_ele = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "vjs-duration-display")))
                current_ele = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "vjs-current-time-display")))
                
                total_time = convertTime(duration_ele.text)
                current_time_val = convertTime(current_ele.text)
                
                # 如果剩余时间少于 5 秒，或者已经看完，则跳过
                if total_time > 0 and (total_time - current_time_val) < 5:
                    print(f"    [跳过] 视频 {v_idx+1} 已完成 ({current_time_val}s / {total_time}s)。")
                    continue
                # -----------------------------

                # 静音 (可选)
                # ...

                # 倍速 (尝试)
                try:
                    speed_btn = driver.find_element(By.CLASS_NAME, "vjs-playback-rate")
                    speed_btn.click()
                    time.sleep(0.5)
                    speed_btn.click() # 切换到 2x
                except:
                    pass

                if total_time == 0:
                    total_time = 1 # 防止进度条报错
                
                # 循环检测直到结束，使用 tqdm 显示进度条
                with tqdm(total=total_time, desc=f"    视频 {v_idx+1}", unit="s", leave=True, ncols=80) as pbar:
                    # 初始化进度条到当前位置
                    if current_time_val > 0:
                        pbar.update(current_time_val)

                    while True:
                        curr_time = convertTime(current_ele.text)
                        
                        # 更新进度条 (根据当前播放时间更新)
                        if curr_time > pbar.n:
                            pbar.update(curr_time - pbar.n)
                            
                        if total_time > 0 and (total_time - curr_time) < 3:
                            pbar.n = total_time # 填满
                            pbar.refresh()
                            print("\n    视频播放完成。")
                            break
                        
                        time.sleep(1) # 提高更新频率
                        
                        # 防暂停检测：如果出现暂停按钮变成了播放按钮，说明视频暂停了，点一下
                        try:
                            play_control = driver.find_element(By.CLASS_NAME, "vjs-play-control")
                            if "vjs-paused" in play_control.get_attribute("class"):
                                play_control.click()
                                # print("    检测到暂停，自动继续播放。") # 不打印防止破坏进度条
                        except:
                            pass
                        
            except Exception as e:
                print(f"    视频 {v_idx+1} 处理出错或已完成: {e}")
                
    except Exception as e:
        print(f"  视频模块出错: {e}")

    # ---------------- PPT 处理 ----------------
    try:
        driver.switch_to.default_content()
        driver.switch_to.frame(iframe1)
        ppt_frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="/ananas/modules/pdf/index.html"]')
        if len(ppt_frames) > 0:
            print(f"  - 检测到 PPT 数量: {len(ppt_frames)}")
            
        for p_idx, _ in enumerate(ppt_frames):
            driver.switch_to.default_content()
            driver.switch_to.frame(iframe1)
            ppt_frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="/ananas/modules/pdf/index.html"]')
            driver.switch_to.frame(ppt_frames[p_idx])
            
            print(f"    正在处理 PPT {p_idx+1}...")
            
            # --- 修改：增加鼠标移动，提高兼容性 ---
            try:
                # 尝试找到 imglook 容器，把鼠标移过去
                img_container = driver.find_element(By.ID, "img")
                mouseMoveTo(img_container, driver)
            except:
                pass
                
            # 1. 模拟阅读 (增加到 50 次，确保足够的时间和覆盖率)
            print("    正在深度模拟阅读 (大幅度多轮滚动)...")
            for _ in range(50):
                pyautogui.scroll(-50) # 加大单次滚动幅度
                time.sleep(0.05)
            
            # 2. --- 关键修改：强制滚动到底部 ---
            # 使用 JS 直接将窗口滚动条置底，确保触发完成状态
            print("    正在强制滚动到底部...")
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                driver.execute_script("window.scrollTo(0, 100000);") 
                # 针对某些特殊的 PPT 容器结构 (如 id=img)
                driver.execute_script("if(document.getElementById('img')) { document.getElementById('img').scrollTop = 100000; }")
            except:
                pass
            
            print("    已触底，停留 5 秒以确认完成...")
            time.sleep(5) # 增加停留时间，确保后台记录
            print("    PPT 处理完毕。")
            
    except Exception as e:
        print(f"  PPT模块出错: {e}")

    # 4. 退出 iframe，准备返回
    driver.switch_to.default_content()

def main():
    print("="*60)
    print("   超星慕课刷课脚本 (Mac 单实例版)")
    print("   特点：只登录一次，自动顺序刷课，无需重复扫码。")
    print("="*60 + "\n")

    # 1. 启动浏览器 (只做一次)
    driver = webdriver.Chrome()
    driver.maximize_window()
    
    # 2. 手动登录引导
    url = "http://mooc.mooc.ucas.edu.cn/mooc-ans/mycourse/studentstudy?chapterId=510034&courseId=350140000032176&clazzid=350140000026834&cpi=350140000200983&enc=51b2637149279c90754aef00a49e2b85&mooc2=1&openc=8d3aa6a2456475bc1dbe2e14019815a0"
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
                
                process_single_chapter(driver, idx)
                
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