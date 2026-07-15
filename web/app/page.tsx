"use client"

import { useState, useCallback, useRef } from "react"
import * as XLSX from "xlsx"
import JSZip from "jszip"
import { useTheme } from "next-themes"
import { Button } from "@/components/ui/button"
import { Moon, Sun } from "lucide-react"

// ─── 后端地址（按实际环境修改端口）─────────────────────
const API_BASE = "http://127.0.0.1:18000"

// ================================================================
// 工具函数
// ================================================================

interface ImageCell {
    zipPath: string
    sheetIndex: number
    row: number
    col: number
}

async function extractImagesFromXlsx(file: File): Promise<{
    images: Map<string, Blob>
    cells: ImageCell[]
}> {
    const zip = await JSZip.loadAsync(file)
    const imageMap = new Map<string, Blob>()
    const cells: ImageCell[] = []

    const imageEntries = Object.keys(zip.files).filter((n) => /^xl\/media\/image\d*\.(png|jpe?g|gif|bmp|webp)$/i.test(n))
    for (const entry of imageEntries) {
        const blob = await zip.files[entry].async("blob")
        imageMap.set(entry, blob)
    }

    const drawingRels = new Map<number, string>()
    for (let i = 1; i <= 6; i++) {
        const relsPath = `xl/worksheets/_rels/sheet${i}.xml.rels`
        const relsXml = await zip.file(relsPath)?.async("string")
        if (!relsXml) continue
        const parser = new DOMParser()
        const doc = parser.parseFromString(relsXml, "text/xml")
        doc.querySelectorAll("Relationship").forEach((el) => {
            const type = el.getAttribute("Type") || ""
            const target = el.getAttribute("Target") || ""
            if (type.includes("drawing")) {
                const drawingPath = "xl/drawings/" + target.replace(/^.*\//, "")
                drawingRels.set(i - 1, drawingPath)
            }
        })
    }

    for (const [sheetIdx, drawingPath] of drawingRels) {
        const drRelsPath = drawingPath.replace(/(\.xml)$/, "_rels/$1.rels")
        const drRelsXml = await zip.file(drRelsPath)?.async("string")
        const embedToFile = new Map<string, string>()
        if (drRelsXml) {
            const parser = new DOMParser()
            const doc = parser.parseFromString(drRelsXml, "text/xml")
            doc.querySelectorAll("Relationship").forEach((el) => {
                const id = el.getAttribute("Id")
                const target = el.getAttribute("Target")
                if (id && target) embedToFile.set(id, "xl/media/" + target.replace(/^.*\//, ""))
            })
        }

        const drawXml = await zip.file(drawingPath)?.async("string")
        if (!drawXml) continue

        const parser = new DOMParser()
        const drawDoc = parser.parseFromString(drawXml, "text/xml")
        // 命名空间元素要用 local-name 匹配
        drawDoc.querySelectorAll("*[local-name='oneCellAnchor'], *[local-name='twoCellAnchor']").forEach((anchor) => {
            const from = anchor.querySelector("*[local-name='from']")
            if (!from) return
            const colEl = from.querySelector("*[local-name='col']")
            const rowEl = from.querySelector("*[local-name='row']")
            const blip = anchor.querySelector("*[local-name='blip']")
            if (!colEl || !rowEl || !blip) return
            const col = parseInt(colEl.textContent || "0", 10)
            const row = parseInt(rowEl.textContent || "0", 10) + 1
            const embedId = blip.getAttribute("r:embed") || blip.getAttribute("embed") || ""
            const zipPath = embedToFile.get(embedId) || ""
            if (zipPath) cells.push({ zipPath, sheetIndex: sheetIdx, row, col })
        })
    }

    return { images: imageMap, cells }
}

interface ParsedExcel {
    basicInfo: Record<string, string>
    changeRecords: Record<string, string>[]
    normativeReferences: Record<string, string | number>[]
    materialList: Record<string, string | number | null>[]
    processStepResources: Record<string, string | number | null>[]
    stepBodies: Record<string, string | number | null>[]
}

function parseExcelData(file: File): Promise<ParsedExcel> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (e) => {
            const wb = XLSX.read(e.target?.result, { type: "array" })
            const sheet = (name: string) => {
                const ws = wb.Sheets[name]
                if (!ws) return []
                return XLSX.utils.sheet_to_json<Record<string, unknown>>(ws)
            }
            const basicRows = sheet("基本信息") as { 字段: string; 值: unknown }[]
            const basicInfo: Record<string, string> = {}
            for (const r of basicRows) {
                const v = r["值"]
                basicInfo[r["字段"]] = v != null ? String(v) : ""
            }
            resolve({
                basicInfo,
                changeRecords: sheet("变更记录") as Record<string, string>[],
                normativeReferences: sheet("规范性引用文件") as Record<string, string | number>[],
                materialList: sheet("物料清单") as Record<string, string | number | null>[],
                processStepResources: sheet("工步流程及作业资源需求") as Record<string, string | number | null>[],
                stepBodies: sheet("工步正文") as Record<string, string | number | null>[],
            })
        }
        reader.onerror = reject
        reader.readAsArrayBuffer(file)
    })
}

const BASIC_FIELD_MAP: Record<string, string> = {
    密级标识: "confidentiality",
    文件类型: "document_type",
    公司: "company",
    制造中心: "manufacturing_center",
    项目号: "project_code",
    "项目名称/产品型号": "project_name",
    工序号: "process_number",
    工序名称: "process_name",
    文件编号: "document_number",
    文件名称: "document_name",
    零部件图号: "part_drawing_number",
    零部件名称: "part_name",
    版本: "version",
    工位: "workstation",
    日期: "effective_date",
    编制: "prepared_by",
    校对: "checked_by",
    审核: "reviewed_by",
    标准化: "standardized_by",
    会签: "countersigned_by",
    批准: "approved_by",
}

const CHANGE_MAP: Record<string, string> = {
    版本号: "version",
    实施日期: "effective_date",
    编制者: "author",
    变更记录: "description",
    文件状态: "status",
}

const REF_MAP: Record<string, string> = {
    序号: "sequence",
    作业指导书编号: "document_number",
    作业指导书名称: "document_name",
}

const MATERIAL_MAP: Record<string, string> = {
    "车种/分组": "vehicle_group",
    序号: "sequence",
    物料编码: "material_code",
    物料名称: "material_name",
    规格型号: "specification",
    数量: "quantity",
    备注: "remark",
}

const RESOURCE_MAP: Record<string, string> = {
    "工步号*": "step_number",
    "工步名称*": "step_name",
    "零部件图号（子图号）": "component_drawing_number",
    "零部件名称（子部件）": "component_name",
    工步标识: "step_marker",
    "设备、工艺装备（计量）": "equipment_tooling",
    规格型号: "equipment_spec",
    作业工种: "work_type",
    作业人数: "worker_count",
    "作业时间(min)": "work_time_minutes",
}

const STEP_BODY_MAP: Record<string, string> = {
    工步号: "step_number",
    工步名称: "step_name",
    动作序号: "action_sequence",
    动作描述: "action_description",
    技术要求: "technical_requirements",
    是否自检: "self_inspection",
    "排版(横/竖)": "layout",
}

function remap<T extends Record<string, unknown>>(rows: Record<string, unknown>[], map: Record<string, string>): T[] {
    return rows.map((row) => {
        const out: Record<string, unknown> = {}
        for (const [cn, en] of Object.entries(map)) {
            out[en] = row[cn]
        }
        return out as T
    })
}

/** Excel 序列化日期 (1900 纪元偏移) → "YYYY-MM-DD" 字符串 */
function excelDateToString(v: unknown): string | null {
    if (v == null) return null
    // 如果是数字（Excel 日期序列号），转为日期字符串
    if (typeof v === "number" && v > 1 && v < 100000) {
        const d = new Date((v - 25569) * 86400 * 1000)
        const yyyy = d.getFullYear()
        const mm = String(d.getMonth() + 1).padStart(2, "0")
        const dd = String(d.getDate()).padStart(2, "0")
        return `${yyyy}-${mm}-${dd}`
    }
    return String(v)
}

/** 将可能为字符串的数字转为整数，无法转换则返回原值 */
function toInt(v: unknown): number | null {
    if (v == null || v === "") return null
    if (typeof v === "number") return Math.round(v)
    if (typeof v === "string") {
        const n = parseInt(v, 10)
        return isNaN(n) ? null : n
    }
    return null
}

/** 将可能为数字的字段转为字符串 */
function toStr(v: unknown): string | null {
    if (v == null || v === "") return null
    return String(v)
}

// ================================================================
// 页面
// ================================================================

type Step = "idle" | "parsing" | "uploading" | "generating" | "done" | "error"

export default function Page() {
    const { resolvedTheme, setTheme } = useTheme()
    const [file, setFile] = useState<File | null>(null)
    const [step, setStep] = useState<Step>("idle")
    const [log, setLog] = useState<string[]>([])
    const [preview, setPreview] = useState<ParsedExcel | null>(null)
    const [apiBase, setApiBase] = useState(API_BASE)
    const logRef = useRef<HTMLPreElement>(null)

    const addLog = useCallback((msg: string) => {
        setLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])
    }, [])

    const handleFile = useCallback(
        async (e: React.ChangeEvent<HTMLInputElement>) => {
            const f = e.target.files?.[0]
            if (!f) return
            setFile(f)
            setStep("parsing")
            setLog([])
            setPreview(null)
            addLog(`解析文件: ${f.name} (${(f.size / 1024 / 1024).toFixed(1)} MB)`)
            try {
                const data = await parseExcelData(f)
                setPreview(data)
                addLog(
                    `解析完成 — 基本信息 ${Object.keys(data.basicInfo).length} 项, ` +
                        `变更记录 ${data.changeRecords.length}, ` +
                        `引用文件 ${data.normativeReferences.length}, ` +
                        `物料 ${data.materialList.length}, ` +
                        `工步资源 ${data.processStepResources.length}, ` +
                        `工步正文 ${data.stepBodies.length}`
                )
                setStep("idle")
            } catch (err: unknown) {
                addLog(`解析失败: ${err instanceof Error ? err.message : String(err)}`)
                setStep("error")
            }
        },
        [addLog]
    )

    const handleGenerate = useCallback(async () => {
        if (!file || !preview) return
        setStep("uploading")
        addLog("──────── 开始处理 ────────")
        try {
            addLog("正在从 Excel 中提取嵌入图片...")
            const { images: imgMap, cells: imgCells } = await extractImagesFromXlsx(file)
            addLog(`找到 ${imgMap.size} 张嵌入图片, ${imgCells.length} 个锚点`)

            addLog("正在上传图片到后端...")
            const form = new FormData()
            for (const [zipPath, blob] of imgMap) {
                const filename = zipPath.replace(/^.*\//, "")
                form.append("files", blob, filename)
            }

            const uploadRes = await fetch(`${apiBase}/api/process-card/images/upload`, {
                method: "POST",
                body: form,
            })
            const uploadJson = await uploadRes.json()
            if (uploadJson.status === "error") throw new Error(`图片上传失败: ${JSON.stringify(uploadJson.errors)}`)
            addLog(`图片上传完成 — ${uploadJson.total_count} 张成功` + (uploadJson.errors?.length ? `, ${uploadJson.errors.length} 张失败` : ""))

            // 基于文件名映射（而非脆弱的索引映射），避免部分上传失败时映射错位
            const zipToId = new Map<string, string>()
            for (const img of uploadJson.images as { image_id: string; original_filename: string }[]) {
                zipToId.set(img.original_filename, img.image_id)
            }

            addLog("正在构建 API 请求数据...")
            const apiJson: Record<string, unknown> = {}

            const basic: Record<string, string | null> = {}
            for (const [cn, en] of Object.entries(BASIC_FIELD_MAP)) basic[en] = preview.basicInfo[cn] || null
            apiJson["basic_info"] = basic

            // 变更记录 — 日期字段从 Excel 序列号转为字符串
            const changeRecords = remap(preview.changeRecords, CHANGE_MAP)
            for (const r of changeRecords) {
                ;(r as Record<string, unknown>)["effective_date"] = excelDateToString((r as Record<string, unknown>)["effective_date"])
            }
            apiJson["change_records"] = changeRecords

            // 引用文件 / 物料 — sequence 确保为整数
            const normativeReferences = remap(preview.normativeReferences, REF_MAP)
            for (const r of normativeReferences) {
                ;(r as Record<string, unknown>)["sequence"] = toInt((r as Record<string, unknown>)["sequence"])
            }
            apiJson["normative_references"] = normativeReferences

            const materialList = remap(preview.materialList, MATERIAL_MAP)
            for (const r of materialList) {
                const m = r as Record<string, unknown>
                m["sequence"] = toInt(m["sequence"])
                m["quantity"] = typeof m["quantity"] === "number" ? m["quantity"] : null
            }
            apiJson["material_list"] = materialList

            // 工步资源 — step_number 确保字符串，worker_count / work_time_minutes 确保整数
            let resourceImgMatchCount = 0
            const resources = remap(preview.processStepResources, RESOURCE_MAP).map((r: Record<string, unknown>, i: number) => {
                r["step_number"] = toStr(r["step_number"])
                r["worker_count"] = toInt(r["worker_count"])
                r["work_time_minutes"] = toInt(r["work_time_minutes"])
                // 优先匹配 col=10（标准图片列），其次匹配该行任意列
                let matched = imgCells.find((c) => c.sheetIndex === 4 && c.row === i + 2 && c.col === 10)
                if (!matched) {
                    matched = imgCells.find((c) => c.sheetIndex === 4 && c.row === i + 2)
                }
                if (matched) resourceImgMatchCount++
                const basename = matched?.zipPath.replace(/^.*\//, "") || ""
                return { ...r, image_id: matched ? zipToId.get(basename) || null : null }
            })
            addLog(`工步资源图片匹配: ${resourceImgMatchCount}/${resources.length}`)
            apiJson["process_step_resources"] = resources

            const bodyColMap: Record<number, string> = {
                7: "image_id",
                8: "image_page_1_id",
                9: "image_page_2_id",
                10: "image_page_3_id",
            }
            let bodyImgMatchCount = 0
            const bodies = remap(preview.stepBodies, STEP_BODY_MAP).map((b: Record<string, unknown>, i: number) => {
                b["step_number"] = toStr(b["step_number"])
                b["action_sequence"] = toStr(b["action_sequence"])
                const imgFields: Record<string, string | null> = {}
                for (const c of imgCells) {
                    if (c.sheetIndex === 5 && c.row === i + 2) {
                        const field = bodyColMap[c.col]
                        if (field) {
                            const basename = c.zipPath.replace(/^.*\//, "")
                            const imgId = zipToId.get(basename)
                            if (imgId) {
                                imgFields[field] = imgId
                                bodyImgMatchCount++
                            }
                        }
                    }
                }
                return { ...b, ...imgFields }
            })
            addLog(`工步正文图片匹配: ${bodyImgMatchCount} 张`)
            apiJson["step_bodies"] = bodies
            addLog(`API 请求构建完成 — ${resources.length} 个工步资源, ${bodies.length} 个工步正文`)

            setStep("generating")
            addLog("正在调用 PDF 生成接口...")
            const genRes = await fetch(`${apiBase}/api/process-card/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(apiJson),
            })
            if (!genRes.ok) {
                const errBody = await genRes.json().catch(() => ({}))
                throw new Error(`生成失败 (HTTP ${genRes.status}): ${JSON.stringify(errBody)}`)
            }

            const pdfBlob = await genRes.blob()
            const url = URL.createObjectURL(pdfBlob)
            const a = document.createElement("a")
            a.href = url
            a.download = (preview.basicInfo["文件编号"] || "process_card") + ".pdf"
            a.click()
            URL.revokeObjectURL(url)
            addLog(`✅ PDF 生成成功! 大小: ${(pdfBlob.size / 1024).toFixed(1)} KB`)
            setStep("done")
        } catch (err: unknown) {
            addLog(`❌ 错误: ${err instanceof Error ? err.message : String(err)}`)
            setStep("error")
        }
    }, [file, preview, apiBase, addLog])

    return (
        <div className="min-h-screen bg-neutral-50 p-6 dark:bg-neutral-950">
            <div className="mx-auto max-w-4xl space-y-5">
                {/* 标题栏 + 主题切换 */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-xl font-bold tracking-tight text-black dark:text-white">工序卡 PDF 生成测试</h1>
                        <p className="mt-1 text-sm text-neutral-500">上传 xlsx → 自动解析数据 & 提取图片 → 调用后端 API → 下载 PDF</p>
                    </div>
                    <button
                        onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
                        className="rounded-lg border border-neutral-200 p-2 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                        title="切换明暗主题"
                    >
                        {resolvedTheme === "dark" ? <Sun className="size-4 text-yellow-400" /> : <Moon className="size-4 text-neutral-600" />}
                    </button>
                </div>

                {/* 后端地址 */}
                <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
                    <label className="mb-1 block text-sm font-medium text-black dark:text-white">后端地址</label>
                    <input
                        className="w-full rounded-md border bg-white px-3 py-1.5 font-mono text-sm text-black dark:bg-neutral-900 dark:text-white"
                        value={apiBase}
                        onChange={(e) => setApiBase(e.target.value)}
                    />
                </div>

                {/* 文件选择 */}
                <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
                    <label className="mb-2 block text-sm font-medium text-black dark:text-white">选择工序卡 Excel 文件 (.xlsx)</label>
                    <input
                        type="file"
                        accept=".xlsx"
                        onChange={handleFile}
                        className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutral-900 file:px-3 file:py-1.5 file:text-xs file:text-white hover:file:bg-neutral-700 dark:file:bg-white dark:file:text-black"
                    />
                    {file && <p className="mt-1 text-xs text-neutral-400">已选择: {file.name}</p>}
                </div>

                {/* 数据预览 + 生成按钮 */}
                {preview && (
                    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
                        <h2 className="mb-2 text-sm font-semibold text-black dark:text-white">数据预览</h2>
                        <div className="grid grid-cols-2 gap-3 text-xs">
                            {[
                                ["基本信息", JSON.stringify(preview.basicInfo, null, 2)],
                                ["变更记录", JSON.stringify(preview.changeRecords.slice(0, 3), null, 2)],
                                ["引用文件", JSON.stringify(preview.normativeReferences.slice(0, 3), null, 2)],
                                ["物料", JSON.stringify(preview.materialList.slice(0, 3), null, 2)],
                                ["工步资源", JSON.stringify(preview.processStepResources.slice(0, 3), null, 2)],
                                ["工步正文", JSON.stringify(preview.stepBodies.slice(0, 3), null, 2)],
                            ].map(([label, content]) => (
                                <div key={label}>
                                    <span className="inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs font-semibold">{label}</span>
                                    <pre className="mt-1 max-h-32 overflow-auto font-mono text-xs break-all text-neutral-700 dark:text-neutral-300">
                                        {content}
                                    </pre>
                                </div>
                            ))}
                        </div>
                        <Button className="mt-4 w-full" onClick={handleGenerate} disabled={step === "uploading" || step === "generating"}>
                            {step === "uploading" ? "正在上传图片..." : step === "generating" ? "正在生成 PDF..." : "上传图片 & 生成 PDF"}
                        </Button>
                    </div>
                )}

                {/* 日志 */}
                <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
                    <h2 className="mb-2 text-sm font-semibold text-black dark:text-white">处理日志</h2>
                    <pre
                        ref={logRef}
                        className="max-h-64 overflow-auto rounded-md bg-neutral-100 p-3 font-mono text-xs break-all whitespace-pre-wrap text-black dark:bg-neutral-900 dark:text-white"
                    >
                        {log.length === 0 ? "等待操作..." : log.join("\n")}
                    </pre>
                </div>

                {step === "done" && (
                    <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
                        ✅ PDF 已生成并开始下载。
                    </div>
                )}
                {step === "error" && (
                    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
                        ❌ 处理出错，请查看上方日志了解详情。
                    </div>
                )}
            </div>
        </div>
    )
}
