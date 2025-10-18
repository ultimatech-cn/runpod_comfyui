import os
import json
import uuid
import runpod
import boto3
import requests
from ComfyUI_API_Wrapper import ComfyUI_API_Wrapper

# --- RunPod S3 & ComfyUI 初始化 ---
# 从环境变量中安全地读取RunPod S3的配置
s3_bucket = os.environ.get('S3_BUCKET')
s3_access_key_id = os.environ.get('S3_ACCESS_KEY_ID')
s3_secret_access_key = os.environ.get('S3_SECRET_ACCESS_KEY')
s3_endpoint_url = os.environ.get('S3_ENDPOINT_URL') # <-- RunPod特有的Endpoint URL

# 创建S3客户端，并明确指向RunPod的S3服务
s3_client = boto3.client(
    's3',
    aws_access_key_id=s3_access_key_id,
    aws_secret_access_key=s3_secret_access_key,
    endpoint_url=s3_endpoint_url # <-- 关键区别：告诉boto3连接到RunPod而不是AWS
)

# ComfyUI 初始化
COMFYUI_URL = "http://127.0.0.1:8188"
client_id = str(uuid.uuid4())
output_path = "/root/comfy/ComfyUI/output"
api = ComfyUI_API_Wrapper(COMFYUI_URL, client_id, output_path)

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

def handler(job):
    job_input = job.get('input', {})
    workflow = job_input.get('workflow')
    if not workflow:
        return {"error": "'workflow'是必需的输入。"}

    # ... (下载和准备输入图片的代码保持不变) ...

    # 寻找输出节点ID
    output_node_id = None
    for node_id, node_data in workflow.items():
        if node_data.get("class_type") == "SaveImage":
            output_node_id = node_id
            break
    if not output_node_id:
        return {"error": "工作流中必须包含一个 'SaveImage' 节点。"}

    try:
        # 执行工作流，获取包含文件名的输出
        output_data = api.queue_prompt_and_get_images(workflow, output_node_id)
        if not output_data:
            return {"error": "工作流未生成任何输出。"}
        
        image_urls = []
        for image_info in output_data:
            filename = image_info.get("filename")
            if filename:
                local_file_path = os.path.join(output_path, image_info.get("subfolder", ""), filename)
                s3_key = f"outputs/{uuid.uuid4()}_{filename}"

                # 上传文件到RunPod S3，并设置为公开可读
                s3_client.upload_file(
                    local_file_path, 
                    s3_bucket, 
                    s3_key,
                    ExtraArgs={'ACL': 'public-read', 'ContentType': 'image/png'}
                )
                
                # --- 关键区别：构建RunPod的公开URL ---
                # 格式: https://<bucket_name>.<endpoint_host>/<key>
                endpoint_host = s3_endpoint_url.replace('https://', '')
                image_url = f"https://{s3_bucket}.{endpoint_host}/{s3_key}"
                image_urls.append(image_url)

        return {"image_urls": image_urls}

    except Exception as e:
        return {"error": f"处理过程中发生未知错误: {str(e)}"}

if __name__ == "__main__":
    if not all([s3_bucket, s3_access_key_id, s3_secret_access_key, s3_endpoint_url]):
        print("警告: RunPod S3环境变量未完全配置，将无法返回URL。")
    print("ComfyUI Dynamic Workflow Worker (RunPod Storage) 启动中...")
    runpod.serverless.start({"handler": handler})
