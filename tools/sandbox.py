import docker
import os
import tarfile
import io
import time
import shutil
import hashlib
import textwrap
from utils.logger import logger
from utils.security import SecurityManager

class DockerSandbox:
    def __init__(self, session_id):
        self.client = docker.from_env()
        
        # 生成容器名
        hash_object = hashlib.md5(session_id.encode("utf-8"))
        safe_hash = hash_object.hexdigest()[:12]
        
        self.container_name = f"sandbox_{safe_hash}"
        self.image_name = "ai-sandbox:latest"
        self.work_dir = "/workspace"
        self.host_upload_dir = "uploads"
        self.host_output_dir = os.path.join("uploads", "outputs")
        os.makedirs(self.host_output_dir, exist_ok=True)

    def _get_or_create_container(self):
        try:
            container = self.client.containers.get(self.container_name)
            if container.status != 'running':
                container.start()
            return container
        except docker.errors.NotFound:
            try:
                container = self.client.containers.run(
                    self.image_name,
                    name=self.container_name,
                    detach=True,
                    tty=True,
                    mem_limit="512m",
                    network_mode="none",
                    working_dir=self.work_dir
                )
                return container
            except Exception as e:
                logger.error(f"创建容器失败: {e}")
                raise e

    def copy_to_container(self, host_path):
        container = self._get_or_create_container()
        filename = os.path.basename(host_path)
        
        with open(host_path, 'rb') as f:
            data = f.read()
            
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            tar_info = tarfile.TarInfo(name=filename)
            tar_info.size = len(data)
            tar.addfile(tar_info, io.BytesIO(data))
        
        tar_stream.seek(0)
        container.put_archive(self.work_dir, tar_stream)
        logger.info(f"已上传 {filename} 到沙箱")
        return filename

    def execute_code(self, code):
        container = self._get_or_create_container()
        
        indented_code = textwrap.indent(code, '    ')

        # === 终极版 Wrapper：递归扫描 + 时间戳检测 ===
        wrapped_code = f"""
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import time
import glob

os.chdir('/workspace')

# 检测所有子目录下的文件
target_patterns = ['*.png', '*.jpg', '*.xlsx', '*.xls', '*.csv', '*.txt', '*.json', '*.pdf', '*.docx']

# 1. 【执行前快照】
pre_snapshot = {{}}
for pattern in target_patterns:
    # recursive=True 确保能扫到子文件夹
    for f in glob.glob(f"**/{{pattern}}", recursive=True):
        try:
            pre_snapshot[f] = os.path.getmtime(f)
        except:
            pass

def save_artifacts():
    try:
        os.sync() 
    except: 
        pass

    if plt.get_fignums():
        filename = 'plot_' + str(int(time.time())) + '.png'
        plt.savefig(filename, bbox_inches='tight')
        print(f'[IMAGE_GENERATED]:{{filename}}')
        plt.close()
    
    # 2. 【执行后对比】
    for pattern in target_patterns:
        for f in glob.glob(f"**/{{pattern}}", recursive=True):
            if 'script.py' in f: continue
            if 'plot_' in f and f.endswith('.png'): continue

            try:
                current_mtime = os.path.getmtime(f)
                
                is_new = f not in pre_snapshot
                is_modified = False
                
                if not is_new:
                    if current_mtime > pre_snapshot[f]:
                        is_modified = True
                
                if is_new or is_modified:
                    # 输出相对路径
                    print(f'[FILE_GENERATED]:{{f}}')
            except:
                pass

try:
{indented_code}
    save_artifacts()
except Exception as e:
    print(f"Runtime Error: {{e}}")
"""
        setup_cmd = self.client.api.exec_create(
            container.id, 
            cmd=["bash", "-c", "cat > script.py"], 
            stdin=True
        )
        sock = self.client.api.exec_start(setup_cmd['Id'], socket=True)
        sock.sendall(wrapped_code.encode('utf-8'))
        sock.close()
        
        result = container.exec_run("python script.py")
        output = result.output.decode('utf-8')
        
        final_output = output
        generated_files = []
        processed_filenames = set() 
        
        lines = output.split('\n')
        clean_lines = []
        
        for line in lines:
            stripped_line = line.strip()
            
            # 图片处理
            if "[IMAGE_GENERATED]:" in stripped_line:
                fname = stripped_line.split(":")[1].strip()
                if fname in processed_filenames: continue
                
                if self._fetch_file(container, fname):
                    generated_files.append(os.path.join(self.host_output_dir, os.path.basename(fname)))
                    processed_filenames.add(fname)
            
            # 文件处理
            elif "[FILE_GENERATED]:" in stripped_line:
                fname = stripped_line.split(":")[1].strip()
                # 兼容子文件夹路径，如 'sub/test.xlsx'
                safe_local_name = fname.replace("/", "_").replace("\\", "_")
                
                if fname in processed_filenames: continue
                
                if self._fetch_file(container, fname, safe_local_name):
                    local_path = os.path.join(self.host_output_dir, safe_local_name)
                    generated_files.append(local_path)
                    processed_filenames.add(fname)
            
            else:
                clean_lines.append(line)

        final_output = "\n".join(clean_lines)
        return final_output.strip(), generated_files

    def _fetch_file(self, container, fname, local_name=None):
        if local_name is None: local_name = fname
        try:
            # 这里的 fname 可能是 'sub/test.xlsx'
            bits, stat = container.get_archive(f"{self.work_dir}/{fname}")
            local_tar_path = os.path.join(self.host_output_dir, local_name + ".tar")
            
            with open(local_tar_path, 'wb') as f:
                for chunk in bits:
                    f.write(chunk)
            
            self._extract_tar(local_tar_path, self.host_output_dir)
            return True
        except Exception as e:
            logger.error(f"提取文件 {fname} 失败: {e}")
            return False

    def _extract_tar(self, tar_path, extract_path):
        try:
            with tarfile.open(tar_path, 'r') as tar:
                # Docker 的 get_archive 提取出来可能包含路径信息
                # 这里为了简单，我们尽量让它平铺在 outputs 目录
                tar.extractall(path=extract_path)
            os.remove(tar_path) 
        except Exception as e:
            logger.error(f"解压失败: {e}")

    def stop(self):
        try:
            c = self.client.containers.get(self.container_name)
            c.stop()
            c.remove()
        except: pass