bl_info = {
    "name": "HTXR Camera Batch Render",
    "author": "ggt",
    "version": (1, 1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > HTXR ； Properties > Render > HTXR",
    "description": "按列表姿态批量渲染图片，或将姿态平均插入序列帧并渲染视频（带进度条）。提供 N 面板与属性编辑器双入口。",
    "category": "Render",
}

import bpy
import os
import math
from bpy.types import PropertyGroup, Operator, Panel, UIList
from bpy.props import (
    StringProperty, BoolProperty, IntProperty, PointerProperty,
    CollectionProperty, FloatVectorProperty
)

# =========================
# 数据结构：单个姿态
# =========================
class HTXR_PoseItem(PropertyGroup):
    name: StringProperty(name="名称", default="Pose")
    loc: FloatVectorProperty(
        name="位置", size=3, subtype='TRANSLATION', unit='LENGTH',
        default=(0.0, 0.0, 0.0)
    )
    rot: FloatVectorProperty(
        name="旋转(XYZ)", size=3, subtype='EULER', unit='ROTATION',
        default=(0.0, 0.0, 0.0)  # 内部弧度
    )

# =========================
# 设置集合（挂 Scene）
# =========================
class HTXR_Settings(PropertyGroup):
    # 基础
    camera: PointerProperty(
        name="摄像机",
        type=bpy.types.Object,
        description="用于渲染的摄像机",
        poll=lambda self, obj: (obj and obj.type == 'CAMERA')
    )
    output_dir: StringProperty(
        name="输出目录",
        subtype='DIR_PATH',
        default=r"D:\工作\HTXR\Output"
    )
    filename_prefix: StringProperty(name="图片前缀", default="view_")
    padding: IntProperty(name="序号位数", min=1, max=6, default=2)

    # 图片渲染覆盖设置
    apply_override: BoolProperty(
        name="覆盖图片渲染设置",
        description="启用后使用下方分辨率与采样覆盖当前场景（用于『渲染图片』）",
        default=True
    )
    res_x: IntProperty(name="宽度", min=8, max=16384, default=2560)
    res_y: IntProperty(name="高度", min=8, max=16384, default=1440)
    samples: IntProperty(name="采样", min=1, max=65536, default=1024)
    restore_scene_camera: BoolProperty(name="渲染后还原场景相机", default=True)

    # 姿态列表
    poses: CollectionProperty(type=HTXR_PoseItem)
    pose_index: IntProperty(default=0)

    # ====== 视频模块 ======
    video_apply_override: BoolProperty(
        name="覆盖视频渲染设置",
        description="启用后使用下方分辨率与采样覆盖当前场景（用于『渲染视频』）",
        default=True
    )
    video_res_x: IntProperty(name="视频宽度", min=8, max=16384, default=2560)
    video_res_y: IntProperty(name="视频高度", min=8, max=16384, default=1440)
    video_samples: IntProperty(name="视频采样", min=1, max=65536, default=1024)

    total_frames: IntProperty(name="总帧数", min=2, max=100000, default=300)
    fps: IntProperty(name="帧率", min=1, max=240, default=30)
    frame_start: IntProperty(name="起始帧", min=0, max=1000000, default=1)
    video_filename: StringProperty(name="视频文件名", default="render.mp4")

# =========================
# UI 列表（简洁，避免撑高）
# =========================
class HTXR_UL_PoseList(UIList):
    bl_idname = "HTXR_UL_pose_list"
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        pose = item
        row = layout.row(align=True)
        row.prop(pose, "name", text="", emboss=False, icon='OUTLINER_OB_EMPTY')
        # 简略信息
        deg = tuple(math.degrees(a) for a in pose.rot)
        sub = layout.row(align=True); sub.alignment = 'RIGHT'
        sub.label(text=f"loc:{pose.loc[0]:.2f},{pose.loc[1]:.2f},{pose.loc[2]:.2f}")
        sub = layout.row(align=True); sub.alignment = 'RIGHT'
        sub.label(text=f"rot:{deg[0]:.1f}°, {deg[1]:.1f}°, {deg[2]:.1f}°")

# =========================
# 列表操作
# =========================
class HTXR_OT_PoseAdd(Operator):
    bl_idname = "htxr.pose_add"; bl_label = "添加姿态"
    from_camera: BoolProperty(default=False)
    def execute(self, context):
        s = context.scene.htxr
        item = s.poses.add()
        item.name = f"Pose {len(s.poses)}"
        if self.from_camera:
            cam = s.camera or context.scene.camera or context.view_layer.objects.active
            if cam and cam.type == 'CAMERA':
                item.loc = cam.location
                item.rot = cam.rotation_euler.to_matrix().to_euler('XYZ')
        s.pose_index = len(s.poses) - 1
        return {'FINISHED'}

class HTXR_OT_PoseRemove(Operator):
    bl_idname = "htxr.pose_remove"; bl_label = "删除姿态"
    def execute(self, context):
        s = context.scene.htxr
        idx = s.pose_index
        if 0 <= idx < len(s.poses):
            s.poses.remove(idx)
            s.pose_index = min(idx, len(s.poses) - 1)
        return {'FINISHED'}

class HTXR_OT_PoseMove(Operator):
    bl_idname = "htxr.pose_move"; bl_label = "移动姿态"
    direction: StringProperty()
    def execute(self, context):
        s = context.scene.htxr; idx = s.pose_index
        if self.direction == 'UP' and idx > 0:
            s.poses.move(idx, idx - 1); s.pose_index -= 1
        elif self.direction == 'DOWN' and idx < len(s.poses) - 1:
            s.poses.move(idx, idx + 1); s.pose_index += 1
        return {'FINISHED'}

class HTXR_OT_PoseClear(Operator):
    bl_idname = "htxr.pose_clear"; bl_label = "清空姿态"
    def execute(self, context):
        s = context.scene.htxr; s.poses.clear(); s.pose_index = 0
        return {'FINISHED'}

class HTXR_OT_PoseFromCamera(Operator):
    bl_idname = "htxr.pose_from_camera"; bl_label = "读取当前相机到选中"
    def execute(self, context):
        s = context.scene.htxr
        if not (0 <= s.pose_index < len(s.poses)): return {'CANCELLED'}
        cam = s.camera or context.scene.camera or context.view_layer.objects.active
        if not (cam and cam.type == 'CAMERA'): return {'CANCELLED'}
        pose = s.poses[s.pose_index]
        pose.loc = cam.location
        pose.rot = cam.rotation_euler.to_matrix().to_euler('XYZ')
        return {'FINISHED'}

class HTXR_OT_PoseQuickEdit(Operator):
    bl_idname = "htxr.pose_quick_edit"; bl_label = "编辑选中姿态…"
    name: StringProperty(name="名称")
    loc: FloatVectorProperty(name="位置", size=3, subtype='TRANSLATION', unit='LENGTH')
    rot_deg: FloatVectorProperty(name="旋转(度)", size=3, subtype='EULER')
    def invoke(self, context, event):
        s = context.scene.htxr
        if not (0 <= s.pose_index < len(s.poses)):
            self.report({'WARNING'}, "请先选中一条姿态。"); return {'CANCELLED'}
        p = s.poses[s.pose_index]
        self.name, self.loc, self.rot_deg = p.name, p.loc[:], tuple(math.degrees(a) for a in p.rot)
        return context.window_manager.invoke_props_dialog(self, width=420)
    def draw(self, context):
        l = self.layout; l.use_property_split = True
        l.prop(self, "name"); l.prop(self, "loc"); l.prop(self, "rot_deg")
    def execute(self, context):
        s = context.scene.htxr; p = s.poses[s.pose_index]
        p.name = self.name; p.loc = self.loc; p.rot = tuple(math.radians(a) for a in self.rot_deg)
        return {'FINISHED'}

# =========================
# 渲染：图片（带进度）
# =========================
class HTXR_OT_RenderSequence(Operator):
    bl_idname = "htxr.render_sequence"; bl_label = "按序渲染图片"
    def execute(self, context):
        scene = context.scene; s = scene.htxr
        cam = s.camera or scene.camera or context.view_layer.objects.active
        if cam is None or cam.type != 'CAMERA':
            self.report({'ERROR'}, "请在面板中选择一个摄像机。"); return {'CANCELLED'}

        out_dir = bpy.path.abspath(s.output_dir).rstrip("\\/"); os.makedirs(out_dir, exist_ok=True)
        # 备份
        orig_cam, orig_fp = scene.camera, scene.render.filepath
        orig_res = (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
        cycles_samples = getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None
        ev = getattr(scene, "eevee", None); eevee_taa = getattr(ev, "taa_render_samples", None) if ev else None

        scene.camera = cam
        if s.apply_override:
            scene.render.resolution_x = s.res_x; scene.render.resolution_y = s.res_y; scene.render.resolution_percentage = 100
            if scene.render.engine == 'CYCLES' and hasattr(scene, "cycles"):
                scene.cycles.samples = s.samples
            elif ev and hasattr(ev, "taa_render_samples"):
                ev.taa_render_samples = s.samples

        total = len(s.poses)
        if total == 0:
            self.report({'WARNING'}, "姿态列表为空。"); 
            scene.camera = orig_cam if s.restore_scene_camera else scene.camera
            scene.render.filepath = orig_fp
            return {'CANCELLED'}

        wm = context.window_manager
        wm.progress_begin(0, total)
        try:
            cam.rotation_mode = 'XYZ'
            for i, pose in enumerate(s.poses, start=1):
                cam.location = pose.loc
                cam.rotation_euler = pose.rot
                fname = f"{s.filename_prefix}{i:0{s.padding}d}"
                scene.render.filepath = os.path.join(out_dir, fname)
                self.report({'INFO'}, f"渲染 {i}/{total} → {scene.render.filepath}")
                bpy.ops.render.render(write_still=True)
                wm.progress_update(i)
        finally:
            wm.progress_end()
            scene.render.filepath = orig_fp
            if s.apply_override:
                scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = orig_res
                if scene.render.engine == 'CYCLES' and hasattr(scene, "cycles") and cycles_samples is not None:
                    scene.cycles.samples = cycles_samples
                elif ev and eevee_taa is not None and hasattr(ev, "taa_render_samples"):
                    ev.taa_render_samples = eevee_taa
            if s.restore_scene_camera:
                scene.camera = orig_cam

        self.report({'INFO'}, "图片批量渲染完成。")
        return {'FINISHED'}

# =========================
# 视频：把姿态平均插入到序列帧
# =========================
class HTXR_OT_InsertKeyframesFromPoses(Operator):
    bl_idname = "htxr.insert_keyframes_from_poses"
    bl_label = "将姿态平均插入到序列帧"
    bl_description = "把姿态平均分布到起始帧~结束帧，自动线性插值"

    def execute(self, context):
        scene = context.scene; s = scene.htxr
        cam = s.camera or scene.camera or context.view_layer.objects.active
        if cam is None or cam.type != 'CAMERA':
            self.report({'ERROR'}, "请在面板中选择一个摄像机。"); return {'CANCELLED'}
        if len(s.poses) < 2:
            self.report({'ERROR'}, "至少需要 2 个姿态用于插值。"); return {'CANCELLED'}

        frame_start = s.frame_start
        frame_end   = s.frame_start + s.total_frames - 1
        scene.frame_start, scene.frame_end = frame_start, frame_end
        step = (frame_end - frame_start) / (len(s.poses) - 1)

        cam.rotation_mode = 'XYZ'
        # 清除已有关键帧（仅清相机TRS更安全：先清动画，再插）
        cam.animation_data_clear()

        for i, pose in enumerate(s.poses):
            f = round(frame_start + step * i)
            cam.location = pose.loc
            cam.rotation_euler = pose.rot
            cam.keyframe_insert(data_path="location", frame=f)
            cam.keyframe_insert(data_path="rotation_euler", frame=f)

        # 统一线性插值
        if cam.animation_data and cam.animation_data.action:
            for fc in cam.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'

        self.report({'INFO'}, f"已插入关键帧：{len(s.poses)} 个，帧区间 {frame_start}~{frame_end}。")
        return {'FINISHED'}

# =========================
# 视频渲染（带进度）
# =========================
class HTXR_OT_RenderVideo(Operator):
    bl_idname = "htxr.render_video"; bl_label = "渲染视频到文件夹"
    def execute(self, context):
        scene = context.scene; s = scene.htxr
        cam = s.camera or scene.camera or context.view_layer.objects.active
        if cam is None or cam.type != 'CAMERA':
            self.report({'ERROR'}, "请在面板中选择一个摄像机。"); return {'CANCELLED'}
        if s.total_frames < 2:
            self.report({'ERROR'}, "总帧数至少为 2。"); return {'CANCELLED'}

        out_dir = bpy.path.abspath(s.output_dir).rstrip("\\/"); os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(s.video_filename)[0] or "render"
        outfile = os.path.join(out_dir, base)

        # 备份
        orig = {
            "camera": scene.camera,
            "filepath": scene.render.filepath,
            "fps": scene.render.fps,
            "fps_base": scene.render.fps_base,
            "res": (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage),
            "file_format": scene.render.image_settings.file_format,
            "ff_fmt": getattr(scene.render, "ffmpeg", None).format if hasattr(scene.render, "ffmpeg") else None,
            "ff_codec": getattr(scene.render, "ffmpeg", None).codec if hasattr(scene.render, "ffmpeg") else None,
            "samples": getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None,
            "eevee_taa": getattr(getattr(scene, "eevee", None), "taa_render_samples", None) if hasattr(scene, "eevee") else None,
            "frame_range": (scene.frame_start, scene.frame_end),
        }

        # 应用
        scene.camera = cam
        scene.frame_start = s.frame_start
        scene.frame_end   = s.frame_start + s.total_frames - 1
        scene.render.fps = s.fps
        scene.render.fps_base = 1.0
        if s.video_apply_override:
            scene.render.resolution_x = s.video_res_x
            scene.render.resolution_y = s.video_res_y
            scene.render.resolution_percentage = 100
            if scene.render.engine == 'CYCLES' and hasattr(scene, "cycles"):
                scene.cycles.samples = s.video_samples
            else:
                ev = getattr(scene, "eevee", None)
                if ev and hasattr(ev, "taa_render_samples"):
                    ev.taa_render_samples = s.video_samples

        # FFMPEG / MP4(H.264)
        scene.render.image_settings.file_format = 'FFMPEG'
        if hasattr(scene.render, "ffmpeg"):
            ff = scene.render.ffmpeg
            ff.format = 'MPEG4'
            ff.codec = 'H264'

        scene.render.filepath = outfile

        # 进度条：用帧回调 + Blender 自带进度
        wm = context.window_manager
        total = scene.frame_end - scene.frame_start + 1
        wm.progress_begin(0, total)

        def _progress_cb(_scene):
            try:
                cur = max(_scene.frame_current - _scene.frame_start + 1, 0)
                wm.progress_update(min(cur, total))
            except Exception:
                pass

        try:
            bpy.app.handlers.frame_change_post.append(_progress_cb)
            bpy.ops.render.render(animation=True)
        finally:
            wm.progress_end()
            try:
                bpy.app.handlers.frame_change_post.remove(_progress_cb)
            except Exception:
                pass
            # 还原
            scene.camera = orig["camera"]
            scene.render.filepath = orig["filepath"]
            scene.render.fps = orig["fps"]; scene.render.fps_base = orig["fps_base"]
            scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = orig["res"]
            scene.render.image_settings.file_format = orig["file_format"]
            if hasattr(scene.render, "ffmpeg"):
                scene.render.ffmpeg.format = orig["ff_fmt"] if orig["ff_fmt"] else scene.render.ffmpeg.format
                scene.render.ffmpeg.codec  = orig["ff_codec"] if orig["ff_codec"] else scene.render.ffmpeg.codec
            if scene.render.engine == 'CYCLES' and hasattr(scene, "cycles") and orig["samples"] is not None:
                scene.cycles.samples = orig["samples"]
            else:
                ev = getattr(scene, "eevee", None)
                if ev and orig["eevee_taa"] is not None and hasattr(ev, "taa_render_samples"):
                    ev.taa_render_samples = orig["eevee_taa"]
            scene.frame_start, scene.frame_end = orig["frame_range"]

        self.report({'INFO'}, f"视频渲染完成：{outfile}.mp4")
        return {'FINISHED'}

# =========================
# ---- 绘制复用：N 面板 & 属性编辑器 ----
# =========================
def draw_main_block(layout, s):
    layout.use_property_split = True
    box = layout.box(); box.label(text="基本设置", icon='CAMERA_DATA')
    box.prop(s, "camera"); box.prop(s, "output_dir")
    row = box.row(align=True); row.prop(s, "filename_prefix"); row.prop(s, "padding")

    box2 = layout.box(); box2.label(text="图片渲染设置", icon='RENDER_STILL')
    box2.prop(s, "apply_override")
    col = box2.column(align=True); col.enabled = s.apply_override
    col.prop(s, "res_x"); col.prop(s, "res_y"); col.prop(s, "samples")
    box2.prop(s, "restore_scene_camera")

    layout.separator()
    row = layout.row(); row.scale_y = 1.4
    row.operator("htxr.render_sequence", icon='RENDER_STILL')

def draw_pose_list_block(layout, s, rows=5):
    row = layout.row()
    row.template_list("HTXR_UL_pose_list", "", s, "poses", s, "pose_index", rows=rows)
    col = row.column(align=True)
    col.operator("htxr.pose_add", text="", icon='ADD').from_camera = False
    op = col.operator("htxr.pose_add", text="", icon='OUTLINER_OB_CAMERA'); op.from_camera = True
    col.operator("htxr.pose_remove", text="", icon='REMOVE')
    col.separator()
    op = col.operator("htxr.pose_move", text="", icon='TRIA_UP');   op.direction = 'UP'
    op = col.operator("htxr.pose_move", text="", icon='TRIA_DOWN'); op.direction = 'DOWN'
    col.separator()
    col.operator("htxr.pose_clear", text="", icon='TRASH')

    layout.separator()
    row = layout.row(align=True)
    row.operator("htxr.pose_from_camera", icon='EYEDROPPER')
    row.operator("htxr.pose_quick_edit", icon='GREASEPENCIL')

def draw_pose_edit_block(layout, s):
    layout.use_property_split = True
    if 0 <= s.pose_index < len(s.poses):
        p = s.poses[s.pose_index]
        box = layout.box()
        box.prop(p, "name")
        col = box.column(align=True); col.prop(p, "loc"); col.prop(p, "rot")
    else:
        layout.label(text="未选中姿态。", icon='INFO')

def draw_video_block(layout, s):
    layout.use_property_split = True
    box = layout.box(); box.label(text="时间设置", icon='SEQUENCE')
    box.prop(s, "frame_start")
    box.prop(s, "total_frames")
    box.prop(s, "fps")

    box2 = layout.box(); box2.label(text="视频渲染设置", icon='RENDER_ANIMATION')
    box2.prop(s, "video_apply_override")
    col = box2.column(align=True); col.enabled = s.video_apply_override
    col.prop(s, "video_res_x"); col.prop(s, "video_res_y"); col.prop(s, "video_samples")
    box2.prop(s, "video_filename")

    layout.separator()
    row = layout.row(align=True)
    row.operator("htxr.insert_keyframes_from_poses", icon='KEY_HLT')
    row = layout.row()
    row.scale_y = 1.2
    row.operator("htxr.render_video", icon='RENDER_ANIMATION')

# =========================
# N 面板（紧凑）
# =========================
class HTXR_PT_Main(Panel):
    bl_label = "Camera Batch Render"
    bl_idname = "HTXR_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HTXR"
    def draw(self, context):
        draw_main_block(self.layout, context.scene.htxr)

class HTXR_PT_PoseList(Panel):
    bl_label = "Poses"
    bl_idname = "HTXR_PT_pose_list"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HTXR"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_pose_list_block(self.layout, context.scene.htxr, rows=5)

class HTXR_PT_PoseEdit(Panel):
    bl_label = "Selected Pose"
    bl_idname = "HTXR_PT_pose_edit"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HTXR"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_pose_edit_block(self.layout, context.scene.htxr)

class HTXR_PT_Video(Panel):
    bl_label = "Video"
    bl_idname = "HTXR_PT_video"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HTXR"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_video_block(self.layout, context.scene.htxr)

# =========================
# 属性编辑器（宽、可滚动）
# =========================
class HTXR_PT_Main_Props(Panel):
    bl_label = "HTXR"
    bl_idname = "HTXR_PT_main_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"  # 出现在“渲染”页签
    def draw(self, context):
        draw_main_block(self.layout, context.scene.htxr)

class HTXR_PT_PoseList_Props(Panel):
    bl_label = "HTXR · Poses"
    bl_idname = "HTXR_PT_pose_list_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_pose_list_block(self.layout, context.scene.htxr, rows=8)

class HTXR_PT_PoseEdit_Props(Panel):
    bl_label = "HTXR · Selected Pose"
    bl_idname = "HTXR_PT_pose_edit_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_pose_edit_block(self.layout, context.scene.htxr)

class HTXR_PT_Video_Props(Panel):
    bl_label = "HTXR · Video"
    bl_idname = "HTXR_PT_video_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        draw_video_block(self.layout, context.scene.htxr)

# =========================
# 注册
# =========================
classes = (
    HTXR_PoseItem,
    HTXR_Settings,
    HTXR_UL_PoseList,
    HTXR_OT_PoseAdd,
    HTXR_OT_PoseRemove,
    HTXR_OT_PoseMove,
    HTXR_OT_PoseClear,
    HTXR_OT_PoseFromCamera,
    HTXR_OT_PoseQuickEdit,
    HTXR_OT_RenderSequence,
    HTXR_OT_InsertKeyframesFromPoses,
    HTXR_OT_RenderVideo,
    HTXR_PT_Main,
    HTXR_PT_PoseList,
    HTXR_PT_PoseEdit,
    HTXR_PT_Video,
    HTXR_PT_Main_Props,
    HTXR_PT_PoseList_Props,
    HTXR_PT_PoseEdit_Props,
    HTXR_PT_Video_Props,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.htxr = PointerProperty(type=HTXR_Settings)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.htxr

if __name__ == "__main__":
    register()
