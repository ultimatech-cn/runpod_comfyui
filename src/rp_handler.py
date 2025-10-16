import os
import json
import uuid
import runpod
import base64
import requests
from ComfyUI_API_Wrapper import ComfyUI_API_Wrapper

# --- 全局常量和初始化 ---
COMFYUI_URL = "http://127.0.0.1:8188"
client_id = str(uuid.uuid4())
output_path = "/root/comfy/ComfyUI/output"
api = ComfyUI_API_Wrapper(COMFYUI_URL, client_id, output_path)

# --- 辅助函数: 下载图片 ---
def download_image(url, save_path):
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"下载图片时出错: {e}")
        return False

# --- RunPod Handler ---
def handler(job):
    job_input = job.get('input', {})

    # 1. 直接从输入中获取整个工作流
    workflow = job_input.get('workflow')
    if not workflow or not isinstance(workflow, dict):
        return {"error": "输入错误: 'workflow' 键是必需的，且其值必须是一个有效的JSON对象。"}

    # 2. (可选) 如果提供了image_url，就自动处理图片加载
    if 'image_url' in job_input:
        image_url = job_input['image_url']
        input_path = "/root/comfy/ComfyUI/input"
        if not os.path.exists(input_path):
            os.makedirs(input_path)
        
        image_filename = f"input_{uuid.uuid4()}.png"
        save_path = os.path.join(input_path, image_filename)

        if not download_image(image_url, save_path):
            return {"error": f"无法从指定的URL下载图片: {image_url}"}

        load_image_node_id = None
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "LoadImage":
                load_image_node_id = node_id
                break
        
        if load_image_node_id:
            workflow[load_image_node_id]["inputs"]["image"] = image_filename
        else:
            return {"error": "提供了 'image_url' 但在工作流中找不到 'LoadImage' 节点。"}

    # 3. 找到最终的输出节点 (SaveImage)
    output_node_id = None
    for node_id, node_data in workflow.items():
        if node_data.get("class_type") == "SaveImage":
            output_node_id = node_id
            break
            
    if not output_node_id:
        return {"error": "工作流中必须包含一个 'SaveImage' 节点作为输出。"}

    try:
        # 4. 执行工作流
        output_data = api.queue_prompt_and_get_images(workflow, output_node_id)
        if not output_data:
             return {"error": "执行超时或工作流未生成任何图片输出。"}
        
        # 5. 将输出图片编码为Base64
        base64_images = []
        for image_info in output_data:
            filename = image_info.get("filename")
            if filename:
                image_bytes = api.get_image(filename, image_info.get("subfolder"), image_info.get("type"))
                base64_encoded_image = base64.b64encode(image_bytes).decode('utf-8')
                base64_images.append(base64_encoded_image)

        return {"images": base64_images}

    except Exception as e:
        return {"error": f"处理过程中发生未知错误: {str(e)}"}

# --- 启动 RunPod Worker ---
if __name__ == "__main__":
    print("ComfyUI Dynamic Workflow Worker (最终版) 启动中...")
    runpod.serverless.start({"handler": handler})
