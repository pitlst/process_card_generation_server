from __future__ import annotations
from pydantic import BaseModel, Field


class ImageUploadResult(BaseModel):
    """单张图片上传结果"""

    image_id: str = Field(description="图片唯一标识，后续在工序卡 JSON 中引用此 ID")
    original_filename: str = Field(description="上传时的原始文件名")
    mime_type: str = Field(description="图片 MIME 类型")
    size_bytes: int = Field(description="图片大小（字节）")


class ImageBatchUploadResponse(BaseModel):
    """批量图片上传响应"""

    status: str = Field(default="ok", description="ok | partial | error")
    images: list[ImageUploadResult] = Field(description="已成功上传的图片列表")
    total_count: int = Field(description="成功上传数量")
    total_size_bytes: int = Field(description="成功上传总大小（字节）")
    errors: list[dict] | None = Field(default=None, description="上传失败的文件列表（仅 status=partial 时出现）")


class InvalidImageReference(BaseModel):
    """无效图片引用详情"""

    field_path: str = Field(description="出现无效引用的字段路径")
    image_id: str = Field(description="被引用但不存在的 image_id")


class BasicInfo(BaseModel):
    """工序卡基本信息（元数据）"""

    confidentiality: str | None = Field(default=None, description="密级标识，如：株机公司普通商密▲5年")
    document_type: str | None = Field(default=None, description="文件类型，如：工艺文件")
    company: str | None = Field(default=None, description="公司名称，如：中车株洲电力机车有限公司")
    manufacturing_center: str | None = Field(default=None, description="制造中心，如：城轨制造中心")
    project_code: str | None = Field(default=None, description="项目号")
    project_name: str | None = Field(default=None, description="项目名称/产品型号")
    process_number: str | None = Field(default=None, description="工序号")
    process_name: str | None = Field(default=None, description="工序名称")
    document_number: str | None = Field(default=None, description="文件编号")
    document_name: str | None = Field(default=None, description="文件名称")
    part_drawing_number: str | None = Field(default=None, description="零部件图号")
    part_name: str | None = Field(default=None, description="零部件名称")
    version: str | None = Field(default=None, description="版本")
    workstation: str | None = Field(default=None, description="工位")
    effective_date: str | None = Field(default=None, description="日期")
    prepared_by: str | None = Field(default=None, description="编制")
    checked_by: str | None = Field(default=None, description="校对")
    reviewed_by: str | None = Field(default=None, description="审核")
    standardized_by: str | None = Field(default=None, description="标准化")
    countersigned_by: str | None = Field(default=None, description="会签")
    approved_by: str | None = Field(default=None, description="批准")


class ChangeRecord(BaseModel):
    """单条变更记录"""

    version: str = Field(description="版本号")
    effective_date: str | None = Field(default=None, description="实施日期")
    author: str | None = Field(default=None, description="编制者")
    description: str | None = Field(default=None, description="变更记录")
    status: str | None = Field(default=None, description="文件状态")


class NormativeReference(BaseModel):
    """规范性引用文件"""

    sequence: int = Field(description="序号")
    document_number: str = Field(description="作业指导书编号")
    document_name: str = Field(description="作业指导书名称")


class MaterialItem(BaseModel):
    """单条物料清单条目"""

    vehicle_group: str | None = Field(default=None, description="车种/分组")
    sequence: int = Field(description="序号")
    material_code: str = Field(description="物料编码")
    material_name: str = Field(description="物料名称")
    specification: str | None = Field(default=None, description="规格型号")
    quantity: float | None = Field(default=None, description="数量")
    remark: str | None = Field(default=None, description="备注")


class ProcessStepResource(BaseModel):
    """工步流程及作业资源需求"""

    step_number: str = Field(description="工步号*")
    step_name: str = Field(description="工步名称*")
    component_drawing_number: str | None = Field(default=None, description="零部件图号（子图号）")
    component_name: str | None = Field(default=None, description="零部件名称（子部件）")
    step_marker: str | None = Field(default=None, description="工步标识（如：▲◆★ 分别代表不同重要等级）")
    equipment_tooling: str | None = Field(default=None, description="设备、工艺装备（计量）")
    equipment_spec: str | None = Field(default=None, description="规格型号")
    work_type: str | None = Field(default=None, description="作业工种")
    worker_count: int | None = Field(default=None, description="作业人数")
    work_time_minutes: int | None = Field(default=None, description="作业时间(min)")
    image_id: str | None = Field(default=None, description="配图 — 先调用图片上传接口获取 image_id 后填入此处")


class StepBody(BaseModel):
    """工步正文（每个工步的具体操作步骤）"""

    step_number: str = Field(description="工步号")
    step_name: str = Field(description="工步名称")
    action_sequence: str = Field(description="动作序号，如 1.1、1.2")
    action_description: str = Field(description="动作描述")
    technical_requirements: str | None = Field(default=None, description="技术要求")
    self_inspection: str | None = Field(default=None, description="是否自检（是/否）")
    layout: str | None = Field(default=None, description="排版(横/竖)")
    image_id: str | None = Field(default=None, description="配图（主图）— 先调用图片上传接口获取 image_id 后填入此处")
    image_page_1_id: str | None = Field(default=None, description="配图页1 — 先调用图片上传接口获取 image_id 后填入此处")
    image_page_2_id: str | None = Field(default=None, description="配图页2 — 先调用图片上传接口获取 image_id 后填入此处")
    image_page_3_id: str | None = Field(default=None, description="配图页3 — 先调用图片上传接口获取 image_id 后填入此处")


class ProcessCardInput(BaseModel):
    """工序卡输入数据（完整结构，对应整个 Excel 工作簿）"""

    basic_info: BasicInfo = Field(description="基本信息")
    change_records: list[ChangeRecord] = Field(default_factory=list, description="变更记录")
    normative_references: list[NormativeReference] = Field(default_factory=list, description="规范性引用文件")
    material_list: list[MaterialItem] = Field(default_factory=list, description="物料清单")
    process_step_resources: list[ProcessStepResource] = Field(default_factory=list, description="工步流程及作业资源需求")
    step_bodies: list[StepBody] = Field(default_factory=list, description="工步正文")
