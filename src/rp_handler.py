import os
import json
import uuid
import runpod
import boto3
import requests
from urllib.parse import urlparse
from ComfyUI_API_Wrapper import ComfyUI_API_Wrapper

# --- 路径和常量定义 ---
COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_BASE_PATH = "/root/comfy/ComfyUI"
INPUT_PATH = os.path.join(COMFYUI_BASE_PATH, "input")
OUTPUT_PATH = os.path.join(COMFYUI_BASE_PATH, "output")

# 确保输入目录存在
os.makedirs(INPUT_PATH, exist_ok=True)

# --- RunPod S3 & ComfyUI 初始化 ---
s3_bucket = os.environ.get('S3_BUCKET')
s3_access_key_id = os.environ.get('S3_ACCESS_KEY_ID')
s3_secret_access_key = os.environ.get('S3_SECRET_ACCESS_KEY')
s3_endpoint_url = os.environ.get('S3_ENDPOINT_URL')

s3_client = None
if all([s3_bucket, s3_access_key_id, s3_secret_access_key, s3_endpoint_url]):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=s3_access_key_id,
        aws_secret_access_key=s3_secret_access_key,
        endpoint_url=s3_endpoint_url
    )

# ComfyUI API 客户端初始化
client_id = str(uuid.uuid4())
api = ComfyUI_API_Wrapper(COMFYUI_URL, client_id, OUTPUT_PATH)

def download_image(url, save_path):
    """从给定的URL下载图片并保存到指定路径。"""
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {e}")
        return False

def handle_input_image_url(job_input, workflow):
    """
    处理输入中的'image_url'：下载图片并更新工作流。
    这是新增的核心功能函数。
    """
    image_url = job_input.get('image_url')
    if not image_url:
        return  # 没有提供image_url，无需操作

    # 1. 在工作流中找到LoadImage节点
    node_id = None
    for n_id, node_data in workflow.items():
        if node_data.get("class_type") == "LoadImage":
            node_id = n_id
            break

    if not node_id:
        print("Warning: 'image_url' was provided, but no 'LoadImage' node was found in the workflow.")
        return

    # 2. 准备下载路径和文件名
    try:
        filename = os.path.basename(urlparse(image_url).path)
        if not filename: # 如果URL路径为空，则生成一个随机文件名
             filename = f"{uuid.uuid4()}.jpg"
    except Exception:
        filename = f"{uuid.uuid4()}.jpg"

    save_path = os.path.join(INPUT_PATH, filename)

    # 3. 下载图片
    print(f"Downloading image from {image_url} to {save_path}")
    if download_image(image_url, save_path):
        # 4. 如果下载成功，用本地文件名更新工作流
        workflow[node_id]['inputs']['image'] = filename
        print(f"Workflow updated. Node '{node_id}' will now use image '{filename}'.")
    else:
        # 如果下载失败，抛出异常以终止任务
        raise IOError(f"Failed to download image from URL: {image_url}")


def handler(job):
    job_input = job.get('input', {})
    workflow = job_input.get('workflow')

    if not workflow:
        return {"error": "'workflow' is a required input."}

    try:
        # --- 新增步骤：处理输入图片URL ---
        # 这个函数会直接修改 `workflow` 字典
        handle_input_image_url(job_input, workflow)

        # 寻找输出节点ID
        output_node_id = None
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "SaveImage":
                output_node_id = node_id
                break
        if not output_node_id:
            return {"error": "Workflow must contain a 'SaveImage' node."}

        # 执行工作流
        output_data = api.queue_prompt_and_get_images(workflow, output_node_id)
        if not output_data:
            return {"error": "Workflow did not produce any output."}

        # 如果未配置S3，则直接返回文件名
        if not s3_client:
            return {"output_files": output_data}
        
        # 上传到S3并返回URL
        image_urls = []
        for image_info in output_data:
            filename = image_info.get("filename")
            if filename:
                local_file_path = os.path.join(OUTPUT_PATH, image_info.get("subfolder", ""), filename)
                s3_key = f"outputs/{uuid.uuid4()}_{filename}"
                
                content_type = 'image/png' # 默认
                if filename.lower().endswith(('.jpg', '.jpeg')):
                    content_type = 'image/jpeg'
                elif filename.lower().endswith('.webp'):
                    content_type = 'image/webp'

                s3_client.upload_file(
                    local_file_path, 
                    s3_bucket, 
                    s3_key,
                    ExtraArgs={'ACL': 'public-read', 'ContentType': content_type}
                )
                
                endpoint_host = s3_endpoint_url.replace('https://', '')
                image_url = f"https://{s3_bucket}.{endpoint_host}/{s3_key}"
                image_urls.append(image_url)

        return {"image_urls": image_urls}

    except Exception as e:
        return {"error": f"An unexpected error occurred during processing: {str(e)}"}

if __name__ == "__main__":
    if not s3_client:
        print("Warning: RunPod S3 environment variables not fully configured. Output will be filenames, not URLs.")
    print("ComfyUI Dynamic Workflow Worker (RunPod Storage) starting...")
    runpod.serverless.start({"handler": handler})
