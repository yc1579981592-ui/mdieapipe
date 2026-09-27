import numpy as np

def calculate_angle(a, b, c):
    """
    计算由三个点构成的夹角 (b为顶点)
    a, b, c 的格式为 [x, y]
    返回值: 角度 (0~180度之间)
    """
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    # 构建向量 ba 和 bc
    ba = a - b
    bc = c - b
    
    # 计算点积和向量长度
    dot_product = np.dot(ba, bc)
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    
    if norm_ba == 0 or norm_bc == 0:
        return 0.0
        
    cosine_angle = dot_product / (norm_ba * norm_bc)
    
    # 使用 clip 避免因为浮点数精度导致的 arccos 超出 [-1, 1] 定义域报错
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    # 计算弧度并转为角度
    angle = np.arccos(cosine_angle)
    angle_degrees = np.degrees(angle)
    
    return angle_degrees
