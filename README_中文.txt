StemSure 0.5.4 使用说明
用途：从米制LAS/LAZ森林点云取得树干候选胸径、位置、拟合中心、几何指标和处理状态。测量不需要人工参考表或专用外部DTM。
安装：python -m pip install stemsure-0.5.4-py3-none-any.whl
已验证平台：Windows，Python3.12.10。软件要求Python>=3.12；其他系统尚未验证。
未分类输入：stemsure --input plot.las --output new_run --ground-class all --stem-class all
指定测高：stemsure --input plot.las --output height137 --ground-class all --stem-class all --breast-height 1.37
已归一化输入：stemsure --input normalized.laz --output normalized_run --normalized --stem-class all
分类输入：stemsure --input classified.las --output classified_run --ground-class 2 --stem-class 1
版本检查：stemsure --version
stemsure与stemsure-reliable使用同一当前实现；python -m stemsure及python -m stemsure_reliable也可调用。旧guard、run、checked命令不再安装，历史0.5.0和0.5.1包完整保留。
输入坐标单位须为米；默认地面分类2、树干分类1，未分类点云显式指定all。--normalized表示Z已是离地高度，不再估计地面。
默认中心测高1.30米，相邻截面低/高0.10米。拟合范围5至70厘米，裁剪半径0.45米，与0.5.1相同。
Python接口：
from pathlib import Path
from stemsure_reliable.cli import run
report = run(Path("plot.las"), Path("new_api_run"), ground_class=None, stem_class=None, normalized=False, seed=20260927, trials=20000, breast_height_m=1.30)
成功时返回字典。取得新输出目录所有权后，处理异常保存failure.json并按原异常类型重新抛出，调用方应捕获异常。已有目录或竞争失败时不写入该目录。CLI处理异常退出码2；命令语法错误由参数解析器处理，不一定生成failure.json。
decisions.csv保留每个生成候选的结果。candidate_id是本次运行内编号，不是永久外业树号。详见OUTPUT_FIELDS.txt。
x_m/y_m和proposal字段为候选提议位置；fitted_center字段为中心截面拟合圆心。保留原空间关联语义，不用拟合中心替换历史评价坐标。
keep表示当前几何检查通过；review表示需检查；reject表示中心截面未取得胸径。keep不代表单株身份已确认或误差概率已校准。
真实大树被低估到拟合范围内时，上限保护可能不触发。坐标平移也可能因网格边界浮点分箱改变提议位置，现有算法保持，不能保证提议坐标逐点平移不变。
截面CSV保存拟合参数和指标，未保存全部原始内点。回查需保留原点云及其SHA。当前没有一键图形复核界面。
run_record.json保存输入SHA、参数、种子、实际测高、依赖版本和源码指纹。目录先原子取得所有权，再计算；竞争失败进程不能向其他任务写入失败记录。
requirements-tested.txt保存本次验证的固定依赖版本，不是含全部平台构建哈希的通用锁文件。
许可：LICENSE.txt为作者已批准的论文复现许可，允许复现和核查本文免费使用；其他科研或商业用途须取得书面授权。这是限制用途的源码可见许可，不称通常意义的开源许可。
授权联系：Qianxi Qu，qqx@caf.ac.cn；Zifeng Tan，13588391788@139.com；Qifu Luan，qifu.luan@caf.ac.cn。联系不等于获得授权，也不意味着必定收费。
第三方依赖和真实森林数据遵循各自许可；包内演示点云为合成数据。CITATION.txt提供作者、软件版本及当前稿件题名；GitHub仓库：https://github.com/flytoee/StemSure。软件DOI尚未分配。
本轮整理：统一入口、目录归属、严格JSON、环境来源记录和中英文说明。拟合、筛选阈值、候选生成及关联字段保持；历史论文结果不改。

0.5.4发布整理：正式许可、论文最终题名、GitHub仓库元数据和论文0.5.1复现文件。克隆仓库后运行python -m pip install .；演示命令python examples/run_example.py。
