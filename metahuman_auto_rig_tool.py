# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import math

# SECTION: constants.py
# -*- coding: utf-8 -*-
"""
네이밍 규칙 + 가이드(뼈대) 데이터 정의
--------------------------------------
좌표는 T-포즈 기준 대략적인 성인 인체 비율(cm, Y-up, 캐릭터는 +Z를 바라봄)이며,
실제로는 GuideBuilder 로 생성 후 사용자가 모델에 맞게 위치를 옮기면 됩니다.
"""

# ---------------------------------------------------------------------------
# 네이밍 규칙
# ---------------------------------------------------------------------------
SIDE_LEFT = "L"
SIDE_RIGHT = "R"
SIDE_CENTER = "C"

SIDE_COLOR = {
    SIDE_LEFT: 6,     # 파랑
    SIDE_RIGHT: 13,   # 빨강
    SIDE_CENTER: 17,  # 노랑
}

GUIDE_PREFIX = "GUIDE_"
JNT_SUFFIX = "_JNT"
CTRL_SUFFIX = "_CTRL"
GRP_SUFFIX = "_GRP"
FK_TAG = "_FK"
IK_TAG = "_IK"


def guide_name(part):
    return f"{GUIDE_PREFIX}{part}"


def jnt_name(part):
    return f"{part}{JNT_SUFFIX}"


def ctrl_name(part):
    return f"{part}{CTRL_SUFFIX}"


def grp_name(part):
    return f"{part}{GRP_SUFFIX}"


def mirror_side(name):
    """이름 앞의 L_/R_ 를 서로 바꿔서 반환."""
    if name.startswith(f"{SIDE_LEFT}_"):
        return SIDE_RIGHT + name[1:]
    if name.startswith(f"{SIDE_RIGHT}_"):
        return SIDE_LEFT + name[1:]
    return name


# ---------------------------------------------------------------------------
# 가이드 체인 정의 : (이름, 부모이름 또는 None, 월드 포지션 (x,y,z))
# 이름에는 사이드 프리픽스가 붙지 않은 "코어 이름" 을 사용하고,
# 센터 파트는 그대로, 좌/우 파트는 L_ / R_ 를 붙여서 생성한다.
# ---------------------------------------------------------------------------

CENTER_CHAIN = [
    ("root",     None,       (0, 100, 0)),
    ("spine_01", "root",     (0, 108, 0)),
    ("spine_02", "spine_01", (0, 116, 0)),
    ("spine_03", "spine_02", (0, 124, 0)),
    ("neck",     "spine_03", (0, 138, 0)),
    ("head",     "neck",     (0, 146, 0)),
    ("head_end", "head",     (0, 160, 0)),
]

# 팔 : 부모가 "spine_03" 인 경우는 센터 체인에 붙는 것이라 사이드 프리픽스를 안 붙임
ARM_CHAIN = [
    ("clavicle", "spine_03", (8, 136, 0)),
    ("shoulder", "clavicle", (18, 136, 0)),
    ("elbow",    "shoulder", (38, 136, 0)),
    ("wrist",    "elbow",    (58, 136, 0)),
    ("hand_end", "wrist",    (64, 136, 0)),
]

FINGER_CHAINS = {
    "thumb":  [("thumb_01", "wrist",    (60, 132, 3)),
               ("thumb_02", "thumb_01", (63, 130, 4)),
               ("thumb_03", "thumb_02", (66, 129, 5))],
    "index":  [("index_01", "wrist",    (63, 133, 1.5)),
               ("index_02", "index_01", (67, 133, 1.5)),
               ("index_03", "index_02", (70, 133, 1.5))],
    "middle": [("middle_01", "wrist",    (63, 133, 0)),
               ("middle_02", "middle_01", (68, 133, 0)),
               ("middle_03", "middle_02", (71, 133, 0))],
    "ring":   [("ring_01", "wrist",   (63, 133, -1.5)),
               ("ring_02", "ring_01", (67, 133, -1.5)),
               ("ring_03", "ring_02", (70, 133, -1.5))],
    "pinky":  [("pinky_01", "wrist",   (63, 133, -3)),
               ("pinky_02", "pinky_01", (66, 133, -3)),
               ("pinky_03", "pinky_02", (68, 133, -3))],
}

# 다리 : 부모가 "root" 인 경우는 센터 체인에 붙는 것
LEG_CHAIN = [
    ("hip",   "root", (9, 100, 0)),
    ("knee",  "hip",  (9, 55, 1)),
    ("ankle", "knee", (9, 12, 0)),
    ("ball",  "ankle", (9, 3, 8)),
    ("toe",   "ball",  (9, 3, 14)),
]

# 리버스 풋(IK 발 롤)에 필요한 추가 가이드. 부모는 ankle.
LEG_FOOT_EXTRA = [
    ("heel",     "ankle", (9, 0, -6)),
    ("toe_tip",  "toe",   (9, 3, 17)),
]

# 사이드 프리픽스가 붙는 파트 이름들 (중복 확인용)
SIDED_PARTS = set()
for _n, _p, _pos in ARM_CHAIN:
    SIDED_PARTS.add(_n)
for _chain in FINGER_CHAINS.values():
    for _n, _p, _pos in _chain:
        SIDED_PARTS.add(_n)
for _n, _p, _pos in LEG_CHAIN:
    SIDED_PARTS.add(_n)
for _n, _p, _pos in LEG_FOOT_EXTRA:
    SIDED_PARTS.add(_n)

CENTER_PARTS = set(n for n, p, pos in CENTER_CHAIN)

# 팔/다리 IK-FK 를 만들 때 사용하는 3-조인트 체인 이름
ARM_IKFK_CHAIN = ["shoulder", "elbow", "wrist"]
LEG_IKFK_CHAIN = ["hip", "knee", "ankle"]

FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]


# SECTION: controls.py
# -*- coding: utf-8 -*-
"""
컨트롤 커브(FK/IK/Pole Vector/Switch) 생성 유틸리티
------------------------------------------------------
모든 컨트롤은 "버퍼(오프셋) 그룹"을 가지며, 버퍼 그룹은 대상 조인트/포지션에
스냅된 후 생성됩니다. 이렇게 하면 컨트롤 자체의 transform 값은 0 근처로
유지되어 애니메이터가 다루기 쉽고, freeze 없이도 안전합니다.
"""



SHAPE_CIRCLE = "circle"
SHAPE_CUBE = "cube"
SHAPE_DIAMOND = "diamond"
SHAPE_ARROW = "arrow"
SHAPE_SPHERE = "sphere"


def _shape_points(shape):
    if shape == SHAPE_DIAMOND:
        return [(0, 1, 0), (1, 0, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0),
                (0, 0, 1), (1, 0, 0), (0, 0, -1), (-1, 0, 0), (0, 0, 1),
                (0, 1, 0), (0, 0, -1), (0, -1, 0), (0, 0, 1)]
    if shape == SHAPE_CUBE:
        return [(-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1),
                (-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1),
                (1, 1, -1), (1, 1, 1), (1, -1, 1), (1, -1, -1), (1, -1, 1),
                (-1, -1, 1)]
    return None


def create_control(name, shape=SHAPE_CIRCLE, radius=4.0, normal=(1, 0, 0),
                    color_side=None, snap_to=None, parent=None):
    """
    컨트롤 커브 + 버퍼 그룹 생성.

    Returns:
        (ctrl, buffer_grp)
    """
    if shape == SHAPE_CIRCLE:
        ctrl = cmds.circle(name=ctrl_name(name), radius=radius, normal=normal,
                            constructionHistory=False)[0]
    elif shape == SHAPE_SPHERE:
        ctrl = cmds.circle(name=ctrl_name(name), radius=radius, normal=(1, 0, 0),
                            constructionHistory=False)[0]
        for n, ax in ((0, (0, 1, 0)), (0, (0, 0, 1))):
            extra = cmds.circle(radius=radius, normal=ax, constructionHistory=False)[0]
            shp = cmds.listRelatives(extra, shapes=True)[0]
            cmds.parent(shp, ctrl, relative=True, shape=True)
            cmds.delete(extra)
    else:
        pts = _shape_points(shape)
        pts = [(p[0] * radius, p[1] * radius, p[2] * radius) for p in pts]
        ctrl = cmds.curve(name=ctrl_name(name), degree=1, point=pts)

    buffer_grp = cmds.group(ctrl, name=grp_name(f"{name}_offset"))

    if snap_to and cmds.objExists(snap_to):
        cst = cmds.parentConstraint(snap_to, buffer_grp, maintainOffset=False)
        cmds.delete(cst)

    if color_side and color_side in SIDE_COLOR:
        set_color(ctrl, SIDE_COLOR[color_side])

    if parent and cmds.objExists(parent):
        cmds.parent(buffer_grp, parent)

    return ctrl, buffer_grp


def set_color(ctrl, color_index):
    shapes = cmds.listRelatives(ctrl, shapes=True) or []
    for s in shapes:
        cmds.setAttr(f"{s}.overrideEnabled", 1)
        cmds.setAttr(f"{s}.overrideColor", color_index)


def add_buffer_group(node, suffix="_offset_GRP"):
    """이미 존재하는 노드 위에 zero-out 버퍼 그룹을 하나 더 추가."""
    parent = cmds.listRelatives(node, parent=True)
    grp = cmds.group(empty=True, name=node.replace(CTRL_SUFFIX, "") + suffix)
    cst = cmds.parentConstraint(node, grp, maintainOffset=False)
    cmds.delete(cst)
    if parent:
        cmds.parent(grp, parent[0])
    cmds.parent(node, grp)
    return grp


def lock_hide(node, attrs=("sx", "sy", "sz", "v")):
    for a in attrs:
        full = f"{node}.{a}"
        if cmds.objExists(full):
            cmds.setAttr(full, lock=True, keyable=False, channelBox=False)


# SECTION: guides.py
# -*- coding: utf-8 -*-
"""
가이드(로케이터) 생성 / 미러 / 정리
------------------------------------
가이드는 실제 조인트를 만들기 전에 사용자가 모델 표면에 맞춰 위치를 조정하는
임시 로케이터입니다. GUIDE_ 프리픽스가 붙습니다.
"""




class GuideBuilder(object):

    def __init__(self, position_overrides=None):
        """
        position_overrides : {full_name: (x,y,z)} 형태의 딕셔너리 (선택).
            full_name 은 사이드 프리픽스가 포함된 이름(예: "L_shoulder", "root")
            이며, 여기에 값이 있으면 constants.py 의 기본 T-포즈 좌표 대신
            이 값으로 가이드를 생성한다. auto_fit.compute_guide_positions() 가
            메쉬의 크기/포즈를 분석해서 이 딕셔너리를 만들어준다.
        """
        self.created = []
        self.position_overrides = position_overrides or {}

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------
    def build_all(self):
        """전신 가이드(센터+팔+손가락+다리) 생성."""
        cmds.undoInfo(openChunk=True)
        try:
            top = self._ensure_group("GUIDES_GRP")

            # 센터 체인
            for name, parent, pos in CENTER_CHAIN:
                pos = self.position_overrides.get(name, pos)
                self._make_guide(name, parent, pos, top)

            # 좌/우 팔
            for side in (SIDE_LEFT, SIDE_RIGHT):
                sign = 1 if side == SIDE_LEFT else -1
                for name, parent, pos in ARM_CHAIN:
                    self._make_sided_guide(side, name, parent, pos, sign, top)
                for finger, chain in FINGER_CHAINS.items():
                    for name, parent, pos in chain:
                        self._make_sided_guide(side, name, parent, pos, sign, top)

            # 좌/우 다리
            for side in (SIDE_LEFT, SIDE_RIGHT):
                sign = 1 if side == SIDE_LEFT else -1
                for name, parent, pos in LEG_CHAIN:
                    self._make_sided_guide(side, name, parent, pos, sign, top)
                for name, parent, pos in LEG_FOOT_EXTRA:
                    self._make_sided_guide(side, name, parent, pos, sign, top)

            cmds.select(clear=True)
            return self.created
        finally:
            cmds.undoInfo(closeChunk=True)

    def _ensure_group(self, name):
        if not cmds.objExists(name):
            cmds.group(empty=True, name=name)
        return name

    def _full_guide_name(self, side, part):
        if part in CENTER_PARTS:
            return guide_name(part)
        return guide_name(f"{side}_{part}")

    def _make_sided_guide(self, side, name, parent, pos, sign, top):
        full_name = f"{side}_{name}"
        parent_name = parent
        if parent in SIDED_PARTS:
            parent_full = f"{side}_{parent}"
        else:
            parent_full = parent  # 센터 파트(예: spine_03, root)
        world_pos = (pos[0] * sign, pos[1], pos[2])
        world_pos = self.position_overrides.get(full_name, world_pos)
        self._make_guide(full_name, parent_full, world_pos, top, use_full_name=True)

    def _make_guide(self, name, parent, pos, top, use_full_name=False):
        g_name = guide_name(name)
        if cmds.objExists(g_name):
            self.created.append(g_name)
            return g_name

        loc = cmds.spaceLocator(name=g_name)[0]
        cmds.setAttr(f"{loc}.localScaleX", 2.0)
        cmds.setAttr(f"{loc}.localScaleY", 2.0)
        cmds.setAttr(f"{loc}.localScaleZ", 2.0)
        cmds.xform(loc, worldSpace=True, translation=pos)

        parent_guide = guide_name(parent) if parent else None
        if parent_guide and cmds.objExists(parent_guide):
            cmds.parent(loc, parent_guide)
        else:
            cmds.parent(loc, top)

        # 색상 (좌/우 구분)
        side = None
        if name.startswith("L_"):
            side = SIDE_LEFT
        elif name.startswith("R_"):
            side = SIDE_RIGHT
        if side:
            shape = cmds.listRelatives(loc, shapes=True)[0]
            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            cmds.setAttr(f"{shape}.overrideColor", SIDE_COLOR[side])

        self.created.append(g_name)
        return g_name

    # ------------------------------------------------------------------
    # 미러 : 왼쪽 가이드 위치를 오른쪽으로 복사 (X 반전)
    # ------------------------------------------------------------------
    def mirror_left_to_right(self):
        left_guides = cmds.ls(f"{GUIDE_PREFIX}{SIDE_LEFT}_*", type="transform")
        mirrored = []
        for lg in left_guides:
            rg = lg.replace(f"{GUIDE_PREFIX}{SIDE_LEFT}_",
                             f"{GUIDE_PREFIX}{SIDE_RIGHT}_")
            if not cmds.objExists(rg):
                continue
            pos = cmds.xform(lg, q=True, worldSpace=True, translation=True)
            cmds.xform(rg, worldSpace=True, translation=(-pos[0], pos[1], pos[2]))
            mirrored.append(rg)
        return mirrored

    # ------------------------------------------------------------------
    # 조회 / 정리
    # ------------------------------------------------------------------
    @staticmethod
    def get_world_positions():
        """{core_name: (x,y,z)} 형태로 모든 가이드 위치 반환."""
        result = {}
        for g in cmds.ls(f"{GUIDE_PREFIX}*", type="transform"):
            core = g[len(GUIDE_PREFIX):]
            result[core] = tuple(cmds.xform(g, q=True, worldSpace=True, translation=True))
        return result

    @staticmethod
    def delete_all():
        if cmds.objExists("GUIDES_GRP"):
            cmds.delete("GUIDES_GRP")
        leftover = cmds.ls(f"{GUIDE_PREFIX}*", type="transform")
        if leftover:
            cmds.delete(leftover)


# SECTION: skeleton.py
# -*- coding: utf-8 -*-
"""
가이드 위치를 바탕으로 실제 바인드용 스켈레톤(조인트) 생성.
"""




class SkeletonBuilder(object):

    def __init__(self):
        # core_name(사이드 프리픽스 포함) -> joint 전체 이름
        self.joints = {}
        # 오리엔트 시 leaf(끝) 취급해서 orient 를 0으로 둘 조인트들
        # (실제 스킨에는 안 쓰지만 방향 계산용 팁 조인트)
        self.tip_only = {"head_end", "hand_end", "toe_tip"}

    # ------------------------------------------------------------------
    def build_from_guides(self, guide_positions):
        """
        guide_positions : {core_name: (x,y,z)} - GuideBuilder.get_world_positions() 결과
        """
        cmds.undoInfo(openChunk=True)
        try:
            root_grp = self._ensure_group("SKELETON_GRP")

            chains = self._flatten_chain_defs()
            # 부모가 먼저 만들어지도록 정렬 (root 우선, 그 다음 자식)
            ordered = self._topo_sort(chains)

            cmds.select(clear=True)
            for core_name, parent_core in ordered:
                if core_name not in guide_positions:
                    continue
                pos = guide_positions[core_name]
                jname = jnt_name(core_name)
                if cmds.objExists(jname):
                    self.joints[core_name] = jname
                    continue
                cmds.select(clear=True)
                jnt = cmds.joint(name=jname, position=pos)
                self.joints[core_name] = jnt

            # 부모 연결
            for core_name, parent_core in ordered:
                if core_name not in self.joints:
                    continue
                jnt = self.joints[core_name]
                if parent_core and parent_core in self.joints:
                    parent_jnt = self.joints[parent_core]
                    if cmds.listRelatives(jnt, parent=True) != [parent_jnt]:
                        cmds.parent(jnt, parent_jnt)
                elif not parent_core:
                    if cmds.listRelatives(jnt, parent=True) != [root_grp]:
                        cmds.parent(jnt, root_grp)

            self._orient_all()
            self._set_bind_pose_labels()
            cmds.select(clear=True)
            return self.joints
        finally:
            cmds.undoInfo(closeChunk=True)

    # ------------------------------------------------------------------
    def _ensure_group(self, name):
        if not cmds.objExists(name):
            cmds.group(empty=True, name=name)
        return name

    def _flatten_chain_defs(self):
        """(core_name, parent_core_name) 튜플 리스트를 좌/우 확장해서 반환."""
        out = []
        for name, parent, pos in CENTER_CHAIN:
            out.append((name, parent))

        for side in (SIDE_LEFT, SIDE_RIGHT):
            for name, parent, pos in ARM_CHAIN:
                p = parent if parent in CENTER_PARTS else f"{side}_{parent}"
                out.append((f"{side}_{name}", p))
            for chain in FINGER_CHAINS.values():
                for name, parent, pos in chain:
                    p = parent if parent in CENTER_PARTS else f"{side}_{parent}"
                    out.append((f"{side}_{name}", p))
            for name, parent, pos in LEG_CHAIN:
                p = parent if parent in CENTER_PARTS else f"{side}_{parent}"
                out.append((f"{side}_{name}", p))
            for name, parent, pos in LEG_FOOT_EXTRA:
                p = parent if parent in CENTER_PARTS else f"{side}_{parent}"
                out.append((f"{side}_{name}", p))
        return out

    def _topo_sort(self, pairs):
        by_name = {n: p for n, p in pairs}
        visited = set()
        ordered = []

        def visit(n):
            if n in visited or n not in by_name:
                return
            visited.add(n)
            p = by_name[n]
            if p and p in by_name:
                visit(p)
            ordered.append((n, by_name[n]))

        for n, _ in pairs:
            visit(n)
        return ordered

    # ------------------------------------------------------------------
    def _orient_all(self):
        """각 체인의 루트에서부터 자식 방향으로 조인트 축을 정렬."""
        chain_roots = ["root"]
        for side in (SIDE_LEFT, SIDE_RIGHT):
            chain_roots.append(f"{side}_clavicle")
            for finger in FINGER_NAMES:
                chain_roots.append(f"{side}_{finger}_01")
            chain_roots.append(f"{side}_hip")

        for core in chain_roots:
            jnt = self.joints.get(core)
            if jnt and cmds.objExists(jnt):
                cmds.joint(jnt, edit=True, orientJoint="xyz",
                           secondaryAxisOrient="yup",
                           zeroScaleOrient=True, children=True)

        # 끝 조인트(자식 없음)는 orient 0 으로 정리
        for core, jnt in self.joints.items():
            if not cmds.listRelatives(jnt, children=True, type="joint"):
                cmds.setAttr(f"{jnt}.jointOrientX", 0)
                cmds.setAttr(f"{jnt}.jointOrientY", 0)
                cmds.setAttr(f"{jnt}.jointOrientZ", 0)

    def _set_bind_pose_labels(self):
        for core, jnt in self.joints.items():
            side_val = 0
            label_name = core
            if core.startswith("L_"):
                side_val, label_name = 1, core[2:]
            elif core.startswith("R_"):
                side_val, label_name = 2, core[2:]
            try:
                cmds.setAttr(f"{jnt}.side", side_val)
                cmds.setAttr(f"{jnt}.type", 18)  # Other
                cmds.setAttr(f"{jnt}.otherType", label_name, type="string")
            except Exception:
                pass

    # ------------------------------------------------------------------
    def get_bind_joints(self):
        """스킨 바인딩에 사용할 조인트만 반환 (팁/보조 조인트 제외)."""
        exclude = set()
        for t in self.tip_only:
            exclude.add(t)
            exclude.add(f"{SIDE_LEFT}_{t}")
            exclude.add(f"{SIDE_RIGHT}_{t}")
        exclude.update({f"{SIDE_LEFT}_heel", f"{SIDE_RIGHT}_heel"})
        return [j for core, j in self.joints.items() if core not in exclude]


# SECTION: auto_fit.py
# -*- coding: utf-8 -*-
"""
메쉬 분석 -> 가이드 자동 배치 (크기 + 포즈 자동 대응)
--------------------------------------------------------
사람 모델의 바운딩박스만으로 다음 두 가지를 추정해서 가이드 템플릿에 반영한다.

1. 크기(스케일) : 모델의 실제 키(bbox 높이)를 기준 템플릿 키(REFERENCE_HEIGHT)와
   비교해서 전신 가이드를 동일 비율로 스케일한다.
2. 포즈(T-포즈 ~ A-포즈 ~ 팔 붙임 포즈) : 좌/우 각각 몸통 중심에서 손끝까지의
   수평 거리(팔의 "펼침 정도")를 키에 대한 비율로 측정해서, 팔이 얼마나
   아래로 내려가 있는지(0=수평 T포즈, 90=완전히 아래로 붙은 포즈)를 추정하고
   어깨를 기준으로 팔/손가락 가이드 전체를 그 각도만큼 회전시킨다.
   좌우를 독립적으로 측정하므로 좌우가 다른 포즈(비대칭 포즈)도 어느 정도
   대응한다.

주의: 이 방식은 바운딩박스 기반의 "휴리스틱"이라 완벽하지 않습니다.
스타일라이즈된 캐릭터, 옷을 입은 메쉬, 팔짱을 낀 포즈 등에서는 부정확할 수
있으니 자동 배치 후 가이드를 눈으로 확인하고 필요하면 손으로 미세 조정하세요.
"""

import math



# constants.CENTER_CHAIN 의 head_end(160) - LEG_FOOT_EXTRA 의 heel(0) 이
# 기준 템플릿의 전체 키(=160 유닛)와 정확히 일치하도록 설계되어 있다.
REFERENCE_HEIGHT = 160.0

# 팔 펼침 비율(좌/우 각각: (extentX * 2) / height) 에 따른 팔 각도 매핑
# ratio >= T_POSE_RATIO           -> 0도  (완전한 T-포즈, 팔이 수평)
# ratio <= ARMS_DOWN_RATIO        -> 90도 (팔이 몸통 옆에 거의 붙음)
# 그 사이는 선형 보간 (A-포즈 등 중간 포즈 자동 대응)
T_POSE_RATIO = 0.90
ARMS_DOWN_RATIO = 0.35


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def get_mesh_bbox(mesh):
    if not cmds.objExists(mesh):
        raise RuntimeError(f"메쉬를 찾을 수 없습니다: {mesh}")
    xmin, ymin, zmin, xmax, ymax, zmax = cmds.exactWorldBoundingBox(mesh)
    return {
        "xmin": xmin, "ymin": ymin, "zmin": zmin,
        "xmax": xmax, "ymax": ymax, "zmax": zmax,
        "height": ymax - ymin,
        "width": xmax - xmin,
        "depth": zmax - zmin,
        "center_x": (xmin + xmax) * 0.5,
        "center_z": (zmin + zmax) * 0.5,
    }


def compute_fit_params(mesh):
    """
    메쉬 바운딩박스로부터 스케일/포즈 파라미터를 계산한다.
    좌(+X)/우(-X) 팔 각도를 독립적으로 추정한다.
    """
    bb = get_mesh_bbox(mesh)
    height = max(bb["height"], 1e-4)

    left_extent = max(bb["xmax"] - bb["center_x"], 0.0)   # L_ = +X 쪽
    right_extent = max(bb["center_x"] - bb["xmin"], 0.0)  # R_ = -X 쪽

    def extent_to_angle(extent):
        ratio = _clamp((extent * 2.0) / height, 0.0, 1.5)
        if ratio >= T_POSE_RATIO:
            return 0.0
        if ratio <= ARMS_DOWN_RATIO:
            return 90.0
        t = (T_POSE_RATIO - ratio) / (T_POSE_RATIO - ARMS_DOWN_RATIO)
        return t * 90.0

    left_angle = extent_to_angle(left_extent)
    right_angle = extent_to_angle(right_extent)

    scale = height / REFERENCE_HEIGHT

    return {
        "scale": scale,
        "center_x": bb["center_x"],
        "center_z": bb["center_z"],
        "floor_y": bb["ymin"],
        "height": height,
        "width": bb["width"],
        "depth": bb["depth"],
        "arm_angle": {SIDE_LEFT: left_angle, SIDE_RIGHT: right_angle},
    }


def _rotate_down(dx, dy, dz, angle_deg):
    """
    어깨 기준 상대좌표(dx,dy,dz)를 "아래로" angle_deg 만큼 굽힌다.
    dx 는 어깨에서 손 방향으로의 부호있는 수평 오프셋(왼팔은 +, 오른팔은 -).
    각도가 커질수록 |dx| 는 줄고(팔이 몸에 붙고) dy 는 더 음수가 된다(팔이 처짐).
    """
    rad = math.radians(angle_deg)
    new_dx = dx * math.cos(rad)
    new_dy = dy * math.cos(rad) - abs(dx) * math.sin(rad)
    return new_dx, new_dy, dz


def compute_guide_positions(mesh):
    """
    GuideBuilder(position_overrides=...) 에 바로 넘길 수 있는
    {full_name: (x,y,z)} 딕셔너리를 계산해서 반환한다.
    """
    fp = compute_fit_params(mesh)
    scale = fp["scale"]
    dx_world, dy_world, dz_world = fp["center_x"], fp["floor_y"], fp["center_z"]

    overrides = {}

    # ---- 센터 체인 : 스케일 + 오프셋만 적용 ----
    for name, parent, pos in CENTER_CHAIN:
        overrides[name] = (
            pos[0] * scale + dx_world,
            pos[1] * scale + dy_world,
            pos[2] * scale + dz_world,
        )

    # 어깨(피벗) 원본 좌표 (사이드 없는 템플릿 값, 항상 +X)
    shoulder_template = next(p for n, _, p in ARM_CHAIN if n == "shoulder")

    for side in (SIDE_LEFT, SIDE_RIGHT):
        sign = 1 if side == SIDE_LEFT else -1
        angle = fp["arm_angle"][side]

        shoulder_mirrored = (shoulder_template[0] * sign,
                              shoulder_template[1], shoulder_template[2])

        def transform_arm_point(pos, _sign=sign, _angle=angle,
                                 _piv=shoulder_mirrored):
            mirrored = (pos[0] * _sign, pos[1], pos[2])
            dx = mirrored[0] - _piv[0]
            dy = mirrored[1] - _piv[1]
            dz = mirrored[2] - _piv[2]
            ndx, ndy, ndz = _rotate_down(dx, dy, dz, _angle)
            local = (_piv[0] + ndx, _piv[1] + ndy, _piv[2] + ndz)
            return (local[0] * scale + dx_world,
                    local[1] * scale + dy_world,
                    local[2] * scale + dz_world)

        for name, parent, pos in ARM_CHAIN:
            overrides[f"{side}_{name}"] = transform_arm_point(pos)
        for finger, chain in FINGER_CHAINS.items():
            for name, parent, pos in chain:
                overrides[f"{side}_{name}"] = transform_arm_point(pos)

        # ---- 다리 : 회전 없이 스케일 + 오프셋만 (포즈 무관, 직립 가정) ----
        for name, parent, pos in LEG_CHAIN:
            mirrored = (pos[0] * sign, pos[1], pos[2])
            overrides[f"{side}_{name}"] = (
                mirrored[0] * scale + dx_world,
                mirrored[1] * scale + dy_world,
                mirrored[2] * scale + dz_world,
            )
        for name, parent, pos in LEG_FOOT_EXTRA:
            mirrored = (pos[0] * sign, pos[1], pos[2])
            overrides[f"{side}_{name}"] = (
                mirrored[0] * scale + dx_world,
                mirrored[1] * scale + dy_world,
                mirrored[2] * scale + dz_world,
            )

    return overrides, fp


def describe_fit(fp):
    h_cm = fp["height"]
    l_a = fp["arm_angle"][SIDE_LEFT]
    r_a = fp["arm_angle"][SIDE_RIGHT]

    def pose_label(a):
        if a < 15:
            return "T-포즈"
        if a < 65:
            return "A-포즈"
        return "팔 붙임 포즈"

    return (f"감지된 높이: {h_cm:.1f}유닛 (스케일 {fp['scale']:.3f}배) | "
            f"왼팔: {pose_label(l_a)}({l_a:.0f}°)  "
            f"오른팔: {pose_label(r_a)}({r_a:.0f}°)")


# SECTION: metahuman_rig.py
# -*- coding: utf-8 -*-
"""
메타휴먼(UE5 MetaHuman / UE Mannequin) 기존 스켈레톤 매핑
------------------------------------------------------------
가이드를 만들어 새 조인트를 생성하는 대신, 이미 모델에 배치되어 있는
메타휴먼 스켈레톤(예: pelvis, spine_01~05, clavicle_l, upperarm_l,
lowerarm_l, hand_l, thumb_01_l ... , thigh_l, calf_l, foot_l, ball_l 등)을
그대로 스캔해서 RigBuilder 가 요구하는 {core_name: 실제 조인트 이름}
딕셔너리를 만들어준다.

표준 UE5/메타휴먼 바디 스켈레톤 네이밍을 기본값으로 사용하되,
1) pelvis 이름이 다른 흔한 변형(대소문자, Hips, root 등)도 자동으로 시도하고
2) 조인트에 네임스페이스가 붙어 있어도(예: "char1:pelvis") 자동으로 감지해서
   나머지 모든 조인트 이름 앞에 같은 네임스페이스를 붙여 찾는다.
그래도 못 찾으면 씬에 있는 조인트 중 이름이 비슷한 것들을 힌트로 보여준다.

이미 스킨 바인딩이 된 메쉬라면, 이 워크플로우는 조인트 계층을 그대로 두고
그 위에 IK/FK 컨트롤만 얹기 때문에(FK/IK 는 blendColors 로 원본 바인드
조인트의 rotate 를 구동) 기존 스킨 웨이트가 깨지지 않는다.
"""



DEFAULT_PELVIS = "pelvis"
DEFAULT_SIDE_SUFFIX = {SIDE_LEFT: "_l", SIDE_RIGHT: "_r"}

# pelvis 필드에 입력한 이름을 못 찾았을 때 자동으로 시도해보는 흔한 변형들
PELVIS_FALLBACK_CANDIDATES = [
    "pelvis", "Pelvis", "PELVIS", "root", "Root", "ROOT",
    "Hips", "hips", "HIPS", "Bip01_Pelvis", "Bip001_Pelvis",
]

# (내부 core 이름, 메타휴먼 조인트 이름 패턴) - {s} 자리에 사이드 서픽스가 들어감
ARM_NAME_MAP = [
    ("clavicle", "clavicle{s}"),
    ("shoulder", "upperarm{s}"),
    ("elbow", "lowerarm{s}"),
    ("wrist", "hand{s}"),
]
LEG_NAME_MAP = [
    ("hip", "thigh{s}"),
    ("knee", "calf{s}"),
    ("ankle", "foot{s}"),
    ("ball", "ball{s}"),
]
FINGER_JOINT_MAP = {
    "thumb": ["thumb_01{s}", "thumb_02{s}", "thumb_03{s}"],
    "index": ["index_metacarpal{s}", "index_01{s}", "index_02{s}", "index_03{s}"],
    "middle": ["middle_metacarpal{s}", "middle_01{s}", "middle_02{s}", "middle_03{s}"],
    "ring": ["ring_metacarpal{s}", "ring_01{s}", "ring_02{s}", "ring_03{s}"],
    "pinky": ["pinky_metacarpal{s}", "pinky_01{s}", "pinky_02{s}", "pinky_03{s}"],
}


def _is_joint(name):
    return cmds.objExists(name) and cmds.objectType(name) == "joint"


def _find_top_ancestor(joint_name):
    """joint_name 에서부터 조인트 타입인 조상만 계속 타고 올라가서 최상위
    조인트를 반환한다. 조인트가 아닌 그룹(예: 다른 에셋과 함께 담긴
    joints_grp)을 만나면 그 아래(조인트까지)에서 멈춘다 - 그래야 관계없는
    형제 노드까지 Global_CTRL 밑으로 딸려 들어가지 않는다."""
    cur = joint_name
    while True:
        parents = cmds.listRelatives(cur, parent=True, type="joint") or []
        if not parents:
            return cur
        cur = parents[0]


def _find_similar_joints(keywords, limit=15):
    """씬에 있는 전체 조인트 중 이름에 키워드가 들어간 것들(힌트용)."""
    all_joints = cmds.ls(type="joint") or []
    kws = [kw.lower() for kw in keywords]
    hits = [j for j in all_joints if any(kw in j.lower() for kw in kws)]
    return hits[:limit]


def _resolve_pelvis(user_input):
    """
    pelvis(루트) 조인트를 찾는다. 사용자가 입력한 이름을 최우선으로 시도하고,
    실패하면 흔한 변형 이름들을, 그다음엔 네임스페이스가 붙은 형태를 시도한다.

    Returns:
        (resolved_joint_name, namespace_prefix) 또는 못 찾으면 (None, None)
        namespace_prefix 는 "" 이거나 "ns:" 형태 (뒤에 다른 조인트 이름을
        이어 붙일 때 그대로 접두어로 사용하면 됨).
    """
    candidates = []
    if user_input:
        candidates.append(user_input)
    for c in PELVIS_FALLBACK_CANDIDATES:
        if c not in candidates:
            candidates.append(c)

    # 1) 네임스페이스 없이 정확히 일치
    for name in candidates:
        if _is_joint(name):
            if ":" in name:
                ns = name.rsplit(":", 1)[0] + ":"
            else:
                ns = ""
            return name, ns

    # 2) 네임스페이스가 붙어 있는 경우 (예: "char1:pelvis")
    for name in candidates:
        matches = cmds.ls(f"*:{name}", type="joint") or []
        if matches:
            full = matches[0]
            ns = full.rsplit(":", 1)[0] + ":"
            return full, ns

    return None, None


def discover_skeleton(pelvis_name=DEFAULT_PELVIS, side_suffix=None):
    """
    씬에서 메타휴먼 표준 네이밍의 조인트를 찾아 RigBuilder 용 딕셔너리로 변환한다.

    Returns:
        joint_map : {core_name: 실제 조인트 이름} (RigBuilder(skeleton_joints=...) 에 바로 사용)
        spine_chain : 스파인/목/머리 FK 체인 core 이름 리스트 (RigBuilder(spine_chain=...) 에 사용)
        skeleton_root : Global_CTRL 밑으로 옮길 최상위 조인트 이름
        report : {"found": [...], "missing": [...], "hint": [...], "namespace": str}  사용자 확인용
    """
    side_suffix = side_suffix or DEFAULT_SIDE_SUFFIX
    joint_map = {}
    found, missing = [], []

    resolved_pelvis, ns = _resolve_pelvis(pelvis_name)
    if not resolved_pelvis:
        hint = _find_similar_joints(["pelvis", "hip", "root"])
        report = {
            "found": [], "missing": [f"root (예상 이름: {pelvis_name})"],
            "hint": hint, "namespace": "",
        }
        return joint_map, [], None, report

    def check(core_name, scene_short_name):
        full_name = f"{ns}{scene_short_name}"
        if _is_joint(full_name):
            joint_map[core_name] = full_name
            found.append(f"{core_name} -> {full_name}")
            return True
        missing.append(f"{core_name} (예상 이름: {full_name})")
        return False

    # ---- 최상위 root 조인트가 pelvis 와 별도로 존재하는지 확인 ----
    # (일부 스켈레톤은 root -> pelvis -> spine... 구조이면서, 다리(thigh)는
    #  pelvis 가 아니라 root 의 자식으로 붙어 있다. 이 경우 root 와 pelvis
    #  둘 다 컨트롤을 만들어서, root_CTRL 이 다리까지 포함한 전신을,
    #  pelvis_CTRL 이 골반/스파인만 추가로 조정할 수 있게 한다.)
    pelvis_parents = cmds.listRelatives(resolved_pelvis, parent=True) or []
    spine_chain = []
    if pelvis_parents and _is_joint(pelvis_parents[0]):
        real_root = pelvis_parents[0]
        joint_map["root"] = real_root
        joint_map["pelvis"] = resolved_pelvis
        found.append(f"root -> {real_root}")
        found.append(f"pelvis -> {resolved_pelvis}")
        spine_chain = ["root", "pelvis"]
        skeleton_root = _find_top_ancestor(real_root)
    else:
        joint_map["root"] = resolved_pelvis
        found.append(f"root -> {resolved_pelvis}")
        spine_chain = ["root"]
        skeleton_root = _find_top_ancestor(resolved_pelvis)

    # ---- 스파인 (spine_01 ~ spine_08, 존재하는 만큼) ----
    for i in range(1, 9):
        short = f"spine_{i:02d}"
        full_name = f"{ns}{short}"
        if _is_joint(full_name):
            joint_map[short] = full_name
            spine_chain.append(short)
            found.append(f"{short} -> {full_name}")
        else:
            break

    # ---- 목 (neck_01, neck_02 ... 또는 단일 neck) ----
    neck_found = False
    for i in range(1, 4):
        short = f"neck_{i:02d}"
        full_name = f"{ns}{short}"
        if _is_joint(full_name):
            joint_map[short] = full_name
            spine_chain.append(short)
            found.append(f"{short} -> {full_name}")
            neck_found = True
    if not neck_found and _is_joint(f"{ns}neck"):
        joint_map["neck"] = f"{ns}neck"
        spine_chain.append("neck")
        found.append(f"neck -> {ns}neck")
    elif not neck_found:
        missing.append(f"neck_01 (또는 neck) (예상 이름: {ns}neck_01)")

    # ---- 머리 ----
    if check("head", "head"):
        spine_chain.append("head")

    # ---- 팔 / 다리 / 손가락 (좌우) ----
    for side in (SIDE_LEFT, SIDE_RIGHT):
        s = side_suffix[side]

        for core, pattern in ARM_NAME_MAP:
            check(f"{side}_{core}", pattern.format(s=s))
        for core, pattern in LEG_NAME_MAP:
            check(f"{side}_{core}", pattern.format(s=s))

        for finger, patterns in FINGER_JOINT_MAP.items():
            # patterns 리스트가 3개(엄지)면 01~03, 4개(나머지)면 00(메타카펄)~03 으로 매핑
            start_idx = 1 if len(patterns) == 3 else 0
            for j, pattern in enumerate(patterns):
                idx = start_idx + j
                core = f"{side}_{finger}_{idx:02d}"
                check(core, pattern.format(s=s))

    report = {"found": found, "missing": missing, "hint": [], "namespace": ns}
    return joint_map, spine_chain, skeleton_root, report


def format_report(report):
    ns = report.get("namespace") or ""
    lines = [f"찾은 조인트: {len(report['found'])}개, 누락: {len(report['missing'])}개"]
    if ns:
        lines.append(f"감지된 네임스페이스: \"{ns}\" (모든 이름 앞에 자동으로 붙여서 찾음)")
    if report["missing"]:
        lines.append("누락된 조인트 (해당 부위는 리그가 생성되지 않습니다):")
        lines.extend(f"  - {m}" for m in report["missing"])
    if report.get("hint"):
        lines.append("씬에서 이름이 비슷한 조인트 (참고용, 위 Pelvis 필드에 "
                     "직접 입력해서 다시 스캔해보세요):")
        lines.extend(f"  - {h}" for h in report["hint"])
    return "\n".join(lines)


# SECTION: rig_builder.py
# -*- coding: utf-8 -*-
"""
컨트롤 리그 빌더
------------------
- 스파인/목/머리 : FK
- 팔/다리 : FK + IK + 스위치 블렌드 (3체인 기법: FK조인트/IK조인트 -> blendColors -> 바인드조인트)
- 다리 : 리버스 풋(IK 발 롤) 포함
- 손가락 : FK + 컬(curl) 속성 자동화
- 전체 스케일 : Global_CTRL 하나 아래로 전체 계층을 모아서 어떤 스케일에도 안전하도록 구성

이 빌더는 조인트가 어떻게 만들어졌는지(가이드로 새로 만든 조인트든, 메타휴먼처럼
이미 배치되어 있던 기존 조인트든) 신경 쓰지 않습니다. 생성자에 넘기는
skeleton_joints 딕셔너리({core_name: 실제 씬의 조인트 이름})만 올바르면 됩니다.
폴벡터 위치는 조인트의 로컬 축 방향에 의존하지 않고 월드 포지션만으로
기하학적으로 계산하므로, 조인트 오리엔트 축 컨벤션이나 캐릭터가 바라보는
방향에 상관없이 동작합니다.
"""

import math



DEFAULT_SPINE_CHAIN = ["root", "spine_01", "spine_02", "spine_03", "neck", "head"]


class RigBuilder(object):

    def __init__(self, skeleton_joints, spine_chain=None, existing_skeleton_root=None):
        """
        skeleton_joints : {core_name: 실제 조인트 이름}
            예) SkeletonBuilder.joints (가이드로 새로 만든 스켈레톤) 또는
                metahuman_rig.discover_skeleton() 의 결과 (기존 스켈레톤 매핑)
        spine_chain : 스파인/목/머리 FK 체인에 사용할 core_name 순서 리스트.
            기본값은 3-스파인 구조(root,spine_01~03,neck,head). 메타휴먼처럼
            spine_01~05 + neck_01/neck_02 구조라면 이 리스트를 그에 맞게 넘기면 됨.
        existing_skeleton_root : 이미 존재하는 스켈레톤을 사용하는 경우, 그
            최상위(부모 없는) 조인트 이름. 넘겨주면 이 조인트를 Global_CTRL
            밑으로 옮겨서 전체 스케일 안전 구조에 포함시킨다. 가이드로 새로
            만든 스켈레톤(SKELETON_GRP)을 쓸 때는 None으로 둔다.
        """
        self.jnt = skeleton_joints
        self.spine_chain = spine_chain or DEFAULT_SPINE_CHAIN
        self.existing_skeleton_root = existing_skeleton_root
        # 실제 조인트 이름 -> core_name 역방향 조회 (부모 조인트에 대응하는
        # 컨트롤/조인트를 동적으로 찾을 때 사용, build_all() 에서 채워짐)
        self._reverse_jnt = {jnt: core for core, jnt in skeleton_joints.items()}
        self.fk_ctrls = []
        self.ik_ctrls = []
        self.all_ctrls = []
        self.switch_ctrls = {}
        # 팔/다리별 FK/IK 매치에 필요한 데이터 (컨트롤, 조인트 등) 저장.
        # {f"{side}_{limb_type}": {...}} - match_and_switch() 에서 사용.
        self.limbs = {}
        self.top_grp = None
        self.global_ctrl = None
        # 모든 컨트롤 반지름에 곱해지는 배율. 아래 고정 반지름 값들(스파인 10,
        # 팔/다리 FK 6/4.5 등)은 기준 키 160유닛 템플릿을 기준으로 설계되었기
        # 때문에, 메타휴먼처럼 실제 스켈레톤 크기가 그것과 많이 다르면(예: 실제
        # 사람 키 cm 단위 등) 컨트롤이 서로 겹칠 정도로 너무 크거나(허리에
        # 컨트롤이 몰려 보이는 원인) 반대로 안 보일 정도로 작아진다. 실제
        # 조인트들의 월드 Y 범위(키)를 측정해서 배율을 구해 모든 컨트롤 크기에
        # 곱해줌으로써 어떤 스케일의 캐릭터에도 비율이 맞는 컨트롤이 생성되게 한다.
        self.radius_scale = self._compute_radius_scale()
        # 빌드가 시작되기 전(=FK/IK blendColors 등 어떤 라이브 커넥션도 아직
        # 존재하지 않는 시점)의 "진짜" 원본 바인드 포즈 월드 포지션을 미리
        # 캐시해둔다. 리버스 풋의 heel/ball 피벗처럼 원본 조인트 위치가
        # 필요한 계산은 반드시 이 캐시를 써야, 빌드가 진행되면서 생기는
        # 어떤 라이브 커넥션/평가 순서 문제와도 완전히 무관하게 항상 안전한
        # 값을 쓸 수 있다.
        self.rest_pos = self._cache_rest_positions()

    # ------------------------------------------------------------------
    def _cache_rest_positions(self):
        rest = {}
        for core, jnt in self.jnt.items():
            if cmds.objExists(jnt):
                rest[core] = cmds.xform(jnt, q=True, worldSpace=True, translation=True)
        return rest

    # ------------------------------------------------------------------
    def _compute_radius_scale(self):
        ys = []
        for jnt in self.jnt.values():
            if cmds.objExists(jnt):
                pos = cmds.xform(jnt, q=True, worldSpace=True, translation=True)
                ys.append(pos[1])
        if len(ys) < 2:
            return 1.0
        height = max(ys) - min(ys)
        if height < 1e-3:
            return 1.0
        scale = height / 160.0
        # 극단적으로 작거나 큰 스케일 값으로 인해 컨트롤이 아예 안 보이거나
        # 화면을 뒤덮는 걸 방지하기 위한 안전 범위
        return max(0.05, min(scale, 20.0))

    # ------------------------------------------------------------------
    # 최상위 구조
    # ------------------------------------------------------------------
    def _build_top_structure(self):
        self.top_grp = "RIG_GRP" if cmds.objExists("RIG_GRP") else \
            cmds.group(empty=True, name="RIG_GRP")

        if not cmds.objExists("Global_CTRL"):
            gctrl, gbuf = create_control("Global", shape=SHAPE_CIRCLE,
                                              radius=45 * self.radius_scale, normal=(0, 1, 0))
            cmds.parent(gbuf, self.top_grp)
            cmds.addAttr(gctrl, longName="GlobalScale", attributeType="float",
                         defaultValue=1.0, minValue=0.001, keyable=True)
            for ax in "XYZ":
                cmds.connectAttr(f"{gctrl}.GlobalScale", f"{gctrl}.scale{ax}")
            lock_hide(gctrl, attrs=("sx", "sy", "sz"))
            self.global_ctrl = gctrl
        else:
            self.global_ctrl = "Global_CTRL"

        # CONTROLS_GRP : 모든 FK/IK/스위치 컨트롤 버퍼그룹의 상위 그룹
        # (FK/IK 듀플리케이트 구동 조인트는 각 리밍의 원본 부모 바인드 조인트 밑에
        #  직접 붙이므로 - _duplicate_chain 참고 - 별도 그룹이 필요 없다)
        for grp in ("CONTROLS_GRP", "NOXFORM_GRP"):
            if not cmds.objExists(grp):
                cmds.group(empty=True, name=grp)
            if cmds.listRelatives(grp, parent=True) != [self.global_ctrl]:
                cmds.parent(grp, self.global_ctrl)

        # 바인드 스켈레톤 루트를 Global_CTRL 아래로
        if self.existing_skeleton_root and cmds.objExists(self.existing_skeleton_root):
            # 메타휴먼처럼 이미 존재하는 스켈레톤을 쓰는 경우 : 그 최상위
            # 조인트 하나만 Global_CTRL 밑으로 옮긴다. (내부 계층 구조는
            # 그대로 유지되므로 기존 스킨 바인딩이 있다면 깨지지 않는다.)
            if cmds.listRelatives(self.existing_skeleton_root, parent=True) != [self.global_ctrl]:
                cmds.parent(self.existing_skeleton_root, self.global_ctrl)
        elif cmds.objExists("SKELETON_GRP"):
            if cmds.listRelatives("SKELETON_GRP", parent=True) != [self.global_ctrl]:
                cmds.parent("SKELETON_GRP", self.global_ctrl)

    # ------------------------------------------------------------------
    def build_all(self):
        cmds.undoInfo(openChunk=True)
        try:
            self._build_top_structure()
            self._build_spine_neck_head()
            for side in (SIDE_LEFT, SIDE_RIGHT):
                self._build_ikfk_limb(side, ARM_IKFK_CHAIN, "arm", ik_shape=SHAPE_CUBE)
                self._build_ikfk_limb(side, LEG_IKFK_CHAIN, "leg", ik_shape=SHAPE_CUBE)
                self._build_reverse_foot(side)
                self._build_clavicle(side)
                self._build_fingers(side)
            cmds.select(clear=True)
        finally:
            cmds.undoInfo(closeChunk=True)

    # ------------------------------------------------------------------
    # 스파인 / 목 / 머리 (FK)
    # ------------------------------------------------------------------
    def _build_spine_neck_head(self):
        chain = [c for c in self.spine_chain if self.jnt.get(c)]
        jnts = [self.jnt[c] for c in chain]
        positions = [cmds.xform(j, q=True, worldSpace=True, translation=True) for j in jnts]
        parent = "CONTROLS_GRP"
        prev_ctrl = None
        for i, core in enumerate(chain):
            jnt = jnts[i]
            # 인접 조인트까지의 실제 거리를 기준으로 반지름을 정한다. 메타휴먼처럼
            # spine_01~05 + neck_01/02 등 스파인 조인트 개수가 많아 서로 촘촘히
            # 붙어 있는 경우, 고정된 반지름(예: 10)을 쓰면 컨트롤끼리 겹쳐서
            # "허리에 컨트롤이 몰려" 보이는 문제가 생긴다. 실제 이웃 조인트와의
            # 거리에 비례하게 만들면 스파인 조인트가 몇 개든 항상 서로 구분되어
            # 보인다.
            neighbor_dists = []
            if i > 0:
                neighbor_dists.append(self._dist(positions[i], positions[i - 1]))
            if i < len(chain) - 1:
                neighbor_dists.append(self._dist(positions[i], positions[i + 1]))
            min_floor = 1.0 * self.radius_scale
            if neighbor_dists:
                radius = max(min(neighbor_dists) * 0.4, min_floor)
            else:
                radius = 10 * self.radius_scale
            if core == "root":
                radius = max(radius, 8 * self.radius_scale)
            # 스파인 링을 수평(normal=Y)이 아니라 옆에서 봤을 때 원이 그대로
            # 보이도록 normal=X 로 세워서, 정면/측면 뷰 모두에서 컨트롤들이
            # 겹쳐 보이지 않고 뚜렷이 구분되게 한다.
            shape = SHAPE_CIRCLE
            ctrl, buf = create_control(core, shape=shape, radius=radius,
                                            normal=(1, 0, 0), color_side=SIDE_CENTER,
                                            snap_to=jnt,
                                            parent=prev_ctrl if prev_ctrl else parent)
            cmds.parentConstraint(ctrl, jnt, maintainOffset=True)
            cmds.scaleConstraint(ctrl, jnt, maintainOffset=True)
            lock_hide(ctrl)
            self.fk_ctrls.append(ctrl)
            self.all_ctrls.append(ctrl)
            prev_ctrl = ctrl

    # ------------------------------------------------------------------
    # 씬의 실제 부모-자식 관계를 그대로 활용하는 헬퍼
    # ------------------------------------------------------------------
    def _real_parent_joint(self, jnt_name, fallback):
        """jnt_name 이 씬에서 실제로 부모로 삼고 있는 조인트 이름을 반환한다.
        (guide 로 새로 만든 스켈레톤이든, 메타휴먼처럼 이미 배치된 스켈레톤
        이든, 항상 씬에 실제로 있는 부모-자식 관계를 그대로 신뢰하므로
        스켈레톤 구조에 대한 가정 없이 항상 정확하다.)"""
        parents = cmds.listRelatives(jnt_name, parent=True) or []
        return parents[0] if parents else fallback

    def _parent_ctrl_for(self, jnt_name, fallback="CONTROLS_GRP"):
        """jnt_name 의 실제 부모 조인트에 대응하는 (이미 만들어진) 컨트롤
        이름을 찾는다. 예: 쇄골 조인트의 실제 부모가 spine_05 조인트라면,
        spine_chain 길이가 3이든 5이든 상관없이 spine_05_CTRL 을 정확히
        찾아서 반환한다."""
        parent_jnt = self._real_parent_joint(jnt_name, None)
        if parent_jnt:
            parent_core = self._reverse_jnt.get(parent_jnt)
            if parent_core:
                # 주의: 변수명을 "ctrl_name" 으로 하면 안 된다. 이 파일이
                # 단일 파일로 합쳐질 때 constants 모듈의 ctrl_name() 함수도
                # "" 접두어가 제거되어 똑같이 "ctrl_name" 이 되므로, 같은
                # 이름의 지역변수에 할당하는 순간 파이썬이 이 함수 전체 안에서
                # ctrl_name 을 지역변수로 취급해버려(UnboundLocalError) 함수
                # 호출이 실패한다. 이름을 다르게 지어서 충돌을 피한다.
                resolved_ctrl_name = ctrl_name(parent_core)
                if cmds.objExists(resolved_ctrl_name):
                    return resolved_ctrl_name
        return fallback

    # ------------------------------------------------------------------
    # 쇄골 (단순 FK, IK 없음)
    # ------------------------------------------------------------------
    def _build_clavicle(self, side):
        core = f"{side}_clavicle"
        jnt = self.jnt.get(core)
        if not jnt:
            return
        parent = self._parent_ctrl_for(jnt)
        ctrl, buf = create_control(core, shape=SHAPE_CIRCLE, radius=6 * self.radius_scale,
                                        normal=(1, 0, 0), color_side=side,
                                        snap_to=jnt, parent=parent)
        cmds.orientConstraint(ctrl, jnt, maintainOffset=True)
        lock_hide(ctrl, attrs=("tx", "ty", "tz", "sx", "sy", "sz", "v"))
        self.fk_ctrls.append(ctrl)
        self.all_ctrls.append(ctrl)

    # ------------------------------------------------------------------
    # 팔 / 다리 : FK + IK + 블렌드 스위치 (3-체인 기법)
    # ------------------------------------------------------------------
    def _duplicate_chain(self, side, chain_cores, tag, attach_parent):
        """
        bind 조인트 체인을 복제해서 독립된 새 체인(FK 또는 IK)을 만든다.

        attach_parent 는 반드시 체인의 첫 조인트가 원래 가지고 있던 "원본 부모"와
        동일한 노드(예: 팔이면 clavicle 바인드 조인트, 다리면 root 바인드 조인트)를
        넘겨야 한다. 그래야 cmds.parent 가 월드 트랜스폼을 보정하면서 rotate 채널에
        엉뚱한 보정값을 구워 넣지 않고(보정량이 0이 되어) FK 컨트롤의 rotate=0 이
        바인드 포즈와 정확히 일치하게 된다. (임의의 빈 그룹에 부모를 붙이면 첫
        조인트의 rotate 에 보정값이 생겨, 이후 컨트롤과 connectAttr 할 때 튀는
        버그가 발생한다.)
        """
        new_chain = []
        prev = None
        for core in chain_cores:
            src = self.jnt[f"{side}_{core}"]
            # src.replace() 로 이름을 만들면, 원본 조인트 이름에 "_JNT" 라는
            # 부분 문자열이 없는 경우(예: 메타휴먼 원본 이름 "MHBody:upperarm_l")
            # replace 가 아무 것도 바꾸지 못해 new_name == src 가 되어 버리고,
            # cmds.duplicate 가 원본과 이름이 겹쳐 자동으로 "...1" 을 붙이면서
            # 이후 parent 호출이 "이미 그 부모의 자식" 경고와 함께 실패한다.
            # 항상 우리 쪽 네이밍 요소(side/core/tag)로만 새 이름을 만들어서
            # 원본 조인트의 실제 이름(네임스페이스 포함)과 무관하게 동작하도록 한다.
            new_name = f"{side}_{core}{tag}{JNT_SUFFIX}"
            dup = cmds.duplicate(src, name=new_name, parentOnly=True)[0]
            # cmds.duplicate(parentOnly=True) 는 기본적으로 원본과 "똑같은 부모"
            # 밑에 복제본을 만든다. 체인의 첫 조인트는 원본의 부모가 이미
            # attach_parent 와 같으므로(= _real_parent_joint 로 구한 실제 부모),
            # 이 시점에 dup 은 이미 attach_parent 의 자식이다. 이럴 때 cmds.parent
            # 를 또 호출하면 "이미 그 부모의 자식" 경고와 함께 아무 것도 옮길 게
            # 없어 RuntimeError 가 발생하므로, 실제로 부모를 바꿔야 할 때만
            # cmds.parent 를 호출한다.
            target_parent = prev if prev else attach_parent
            current_parent = cmds.listRelatives(dup, parent=True) or []
            if current_parent != [target_parent]:
                cmds.parent(dup, target_parent)
            # cmds.duplicate 는 원본 조인트의 회전 제한(rotate limit) 속성도
            # 그대로 복사한다. 메타휴먼 등 원본 스켈레톤에 회전 제한이 걸려
            # 있으면, 이 듀플리케이트는 IK/FK 솔버가 자유롭게 굽힐 수 있어야
            # 하는 "구동용" 조인트인데도 원본의 제한을 그대로 물려받아 IK
            # 솔버가 목표 위치까지 도달하지 못하고 다리/팔이 엉뚱한 곳으로
            # 튀는 원인이 될 수 있다. 구동용 체인에는 회전 제한이 있으면 안
            # 되므로 항상 꺼둔다.
            for ax in "XYZ":
                for lim in ("min", "max"):
                    attr = f"{dup}.{lim}Rot{ax}LimitEnable"
                    if cmds.objExists(attr):
                        cmds.setAttr(attr, 0)
            new_chain.append(dup)
            prev = dup
        # 구동용 체인이므로 항상 숨김 (부모 노드를 숨기면 자식 체인 전체가 뷰포트에서 숨겨짐)
        cmds.setAttr(f"{new_chain[0]}.visibility", 0)
        return new_chain

    @staticmethod
    def _dist(a, b):
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))

    @staticmethod
    def _world_offset_in_local_space(node, world_pos):
        """world_pos(월드 좌표)를 node 의 "지금 이 순간" 월드 매트릭스 기준
        로컬(상대) 좌표로 변환해서 반환한다. node 가 나중에 다른 회전을
        갖게 되더라도, 이 상대 오프셋을 그 새 매트릭스에 다시 곱하면
        (아래 _local_offset_to_world) 항상 "node 기준으로 같은 상대 위치"를
        재현할 수 있다 - 리버스 풋 피벗이 ik_ctrl 회전에 따라 지렛대처럼
        엉뚱한 곳으로 튀는 문제를 근본적으로 막기 위한 용도."""
        m = om2.MMatrix(cmds.xform(node, q=True, worldSpace=True, matrix=True))
        p = om2.MPoint(world_pos[0], world_pos[1], world_pos[2]) * m.inverse()
        return (p.x, p.y, p.z)

    @staticmethod
    def _local_offset_to_world(node, local_offset):
        """_world_offset_in_local_space 의 역변환."""
        m = om2.MMatrix(cmds.xform(node, q=True, worldSpace=True, matrix=True))
        p = om2.MPoint(local_offset[0], local_offset[1], local_offset[2]) * m
        return (p.x, p.y, p.z)

    @staticmethod
    def _safe_ik_target(start_pos, target_pos, max_reach):
        """target_pos 가 start_pos 로부터 max_reach(팔다리 최대 리치)의 99%
        이상 떨어져 있으면, ikRPsolver 가 "완전히 뻗은" 특이점 근처에서
        불안정해지는 것을 막기 위해 target 을 살짝 start_pos 쪽으로 당겨서
        반환한다. 그 이내면 원래 값을 그대로 반환한다."""
        delta = tuple(target_pos[i] - start_pos[i] for i in range(3))
        dist = math.sqrt(sum(c * c for c in delta))
        safe_reach = max_reach * 0.99
        if dist > safe_reach and dist > 1e-6:
            scale = safe_reach / dist
            return tuple(start_pos[i] + delta[i] * scale for i in range(3))
        return target_pos

    @staticmethod
    def _pole_vector_position(start_pos, mid_pos, end_pos, distance):
        """
        start/mid/end 세 점의 월드 포지션만으로(조인트 축 방향과 무관하게)
        폴벡터 위치를 기하학적으로 계산한다.
        mid 를 start-end 직선에 투영한 뒤, 그 투영점에서 mid 로 향하는
        방향(팔/다리가 굽혀진 방향)으로 distance 만큼 떨어진 지점을 반환한다.
        반환값 : (pole_vector_world_pos, 정규화된 방향벡터)

        주의: 이 함수는 일부러 조인트 이름/로컬축을 전혀 참조하지 않고 순수
        월드 좌표(포지션)만 사용한다. 이전 버전은 팔다리가 거의 일자로 펴져
        굽힘 방향을 기하학적으로 알 수 없을 때, 조인트의 "로컬 축"을 대체
        기준으로 썼는데, 그 조인트가 빌드 시점 이후 IK 로 계속 회전해온
        상태라면(런타임에 FK<->IK 를 전환할 때처럼) 그 로컬 축 자체가 더 이상
        "깨끗한" 기준이 아니게 되어, 빌드 때와 전환할 때 서로 다른(심지어
        양쪽 다리가 이상하게 도는) 결과를 낼 수 있었다. 순수 포지션 기반
        계산은 항상 결정적이고, 왼쪽/오른쪽 조인트 오리엔트가 어떻게
        미러링되어 있든, 빌드 시점이든 나중에 전환할 때든 항상 동일한
        결과를 낸다.
        """
        chord = tuple(end_pos[i] - start_pos[i] for i in range(3))
        chord_len_sq = sum(c * c for c in chord)
        chord_len = math.sqrt(chord_len_sq)
        if chord_len_sq < 1e-6:
            proj = mid_pos
        else:
            rel = tuple(mid_pos[i] - start_pos[i] for i in range(3))
            t = sum(rel[i] * chord[i] for i in range(3)) / chord_len_sq
            proj = tuple(start_pos[i] + chord[i] * t for i in range(3))

        dir_vec = tuple(mid_pos[i] - proj[i] for i in range(3))
        dir_len = math.sqrt(sum(c * c for c in dir_vec))
        # 다리처럼 체인이 거의 수직(월드 업벡터와 거의 평행)이면, 월드
        # 업벡터와의 외적은 거의 0에 가까운 아주 작은/불안정한 값이 된다.
        # 판정 기준을 체인 길이에 비례한 값으로 넉넉하게 잡아서(거의 일자인
        # 경우를 더 폭넓게 잡음) 아래 fallback 을 쓰도록 한다.
        straight_threshold = max(1e-4, chord_len * 0.02)
        if dir_len < straight_threshold:
            # 체인 자체가 어느 축에 가까운지 보고, 외적 기준(up 벡터)을
            # 체인 방향과 거의 평행하지 않은 쪽으로 고른다.
            #
            # 중요: 다리(체인이 거의 수직, chord ~ world Y)일 때 up 을 월드 Z 로
            # 쓰면 cross(chord, up) 이 월드 X(옆) 방향이 되어버린다 - 무릎은
            # 옆이 아니라 "앞"(월드 Z)으로 굽혀야 하는데, 그러면 폴벡터가 완전히
            # 잘못된 평면(옆면)에 놓여서 IK 로 전환할 때마다 무릎이 옆으로/도는
            # 것처럼 보이는 버그가 생긴다(실제로 확인됨 - "IK 로 전환할 때만
            # 무릎이 돈다"는 증상과 정확히 일치). cross(chord, up) 이 월드 Z(앞)가
            # 나오게 하려면, chord 가 수직(월드 Y)일 때는 up 을 월드 X 로 써야
            # 한다: cross((0,-1,0),(1,0,0)) = (0,0,1). 팔(체인이 거의 수평,
            # chord ~ world X)일 때는 기존대로 월드 Y 를 up 으로 쓰면
            # cross((1,0,0),(0,1,0)) = (0,0,1) 로 마찬가지로 앞을 향한다.
            # 이 판정은 순수 월드 좌표(체인 방향)만 보고 왼쪽/오른쪽에 항상
            # 똑같이 적용되므로 결과도 항상 좌우 일관되게 나온다.
            chord_unit = tuple(c / chord_len for c in chord) if chord_len > 1e-6 else (0.0, 1.0, 0.0)
            up = (1.0, 0.0, 0.0) if abs(chord_unit[1]) > 0.9 else (0.0, 1.0, 0.0)
            cross = (chord[1] * up[2] - chord[2] * up[1],
                     chord[2] * up[0] - chord[0] * up[2],
                     chord[0] * up[1] - chord[1] * up[0])
            cross_len = math.sqrt(sum(c * c for c in cross))
            if cross_len > 1e-4:
                dir_vec, dir_len = cross, cross_len
            else:
                dir_vec, dir_len = (0.0, 0.0, 1.0), 1.0

        unit = tuple(c / dir_len for c in dir_vec)
        pos = tuple(mid_pos[i] + unit[i] * distance for i in range(3))
        return pos, unit

    def _build_clean_ik_chain(self, side, limb_type, ik_jnts, attach_parent):
        """ik_jnts 는 원본 스켈레톤을 복제한 것이라 조인트 오리엔트도 그대로
        물려받는데, 메타휴먼처럼 오른쪽이 왼쪽과 조인트 오리엔트가 180도
        가까이 미러링되어 있는 스켈레톤(실제로 진단해 보니 thigh_r 의
        jointOrient Z 가 thigh_l 대비 약 180도 뒤집혀 있었음 - 좌우 대칭을
        위한 정상적인 컨벤션)에서는 그 조인트 위에서 직접 ikRPsolver 를
        풀면 마야가 완전히 잘못된 해를 낼 수 있다. 이게 바로 왼쪽 다리는
        멀쩡한데 오른쪽 다리만(또는 팔만) 깨지는 대표적인 원인이다.

        그래서 IK 솔버는 원본 조인트가 아니라, 같은 위치에 있지만 체인
        방향만 보고 새로 "깨끗하게" 오리엔트한 별도의 프록시 체인 위에서
        풀고, 그 결과 회전을 orientConstraint 로 원래 ik_jnts 에 옮긴다
        (오리엔트 차이는 orientConstraint 가 자동으로 보정하므로 안전하다).
        이 프록시는 순수하게 월드 포지션(체인이 향하는 방향)만 보고
        계산되므로, 원본 스켈레톤의 좌우 미러링 컨벤션과 무관하게 왼쪽/
        오른쪽 모두 항상 동일한 방식으로 안정적으로 동작한다."""
        clean_chain = []
        cmds.select(clear=True)
        for jnt in ik_jnts:
            pos = cmds.xform(jnt, q=True, worldSpace=True, translation=True)
            name = jnt.replace(IK_TAG, f"{IK_TAG}Clean")
            new_jnt = cmds.joint(name=name, position=pos)
            clean_chain.append(new_jnt)

        # 체인이 거의 수직(다리처럼)이면 secondaryAxisOrient 기준을 월드 Y 로
        # 쓰면 그 자체가 체인 방향과 거의 평행해져서(=또 다른 특이점) 오리엔트
        # 계산이 불안정해질 수 있다. 체인 방향과 덜 평행한 축을 골라 쓴다.
        p0 = cmds.xform(clean_chain[0], q=True, worldSpace=True, translation=True)
        p2 = cmds.xform(clean_chain[-1], q=True, worldSpace=True, translation=True)
        chain_dir = tuple(p2[i] - p0[i] for i in range(3))
        cl = math.sqrt(sum(c * c for c in chain_dir))
        chain_dir = tuple(c / cl for c in chain_dir) if cl > 1e-6 else (0.0, 1.0, 0.0)
        secondary = "zup" if abs(chain_dir[1]) > 0.9 else "yup"

        cmds.joint(clean_chain[0], edit=True, orientJoint="xyz",
                   secondaryAxisOrient=secondary, zeroScaleOrient=True, children=True)
        cmds.setAttr(f"{clean_chain[-1]}.jointOrient", 0, 0, 0, type="double3")
        cmds.parent(clean_chain[0], attach_parent)
        cmds.setAttr(f"{clean_chain[0]}.visibility", 0)

        for src, dst in zip(clean_chain, ik_jnts):
            cmds.orientConstraint(src, dst, maintainOffset=True)
        return clean_chain

    def _build_ikfk_limb(self, side, chain_cores, limb_type, ik_shape):
        bind_jnts = [self.jnt[f"{side}_{c}"] for c in chain_cores]

        # 체인의 첫 조인트가 씬에서 실제로 붙어있는 부모 조인트를 그대로
        # 재사용해서 FK/IK 듀플리케이트 체인을 붙인다 (위 _duplicate_chain
        # 설명 참고). 어떤 조인트가 진짜 부모인지 가정하지 않고 항상 씬의
        # 실제 계층을 그대로 물어보므로, 팔은 쇄골 밑, 다리는 골반 밑처럼
        # "보통 그럴 것"이라 가정했던 스켈레톤 구조와 다르더라도(예: 다리가
        # pelvis 가 아니라 그 위의 root 조인트에 바로 붙어있는 메타휴먼
        # 스켈레톤) 항상 정확하게 동작한다.
        attach_parent = self._real_parent_joint(bind_jnts[0], "CONTROLS_GRP")

        fk_jnts = self._duplicate_chain(side, chain_cores, FK_TAG, attach_parent)
        ik_jnts = self._duplicate_chain(side, chain_cores, IK_TAG, attach_parent)

        # ---------------- FK 컨트롤 ----------------
        prev_ctrl = None
        fk_ctrls_this_limb = []
        for i, core in enumerate(chain_cores):
            name = f"{side}_{core}{FK_TAG}"
            radius = (6 if i == 0 else 4.5) * self.radius_scale
            ctrl, buf = create_control(name, shape=SHAPE_CIRCLE, radius=radius,
                                            normal=(1, 0, 0), color_side=side,
                                            snap_to=fk_jnts[i],
                                            parent=(prev_ctrl if prev_ctrl else "CONTROLS_GRP"))
            # connectAttr 대신 orientConstraint(maintainOffset=True) 를 사용해서,
            # 원본 조인트의 bind-pose rotate 값이 정확히 0 이 아니어도(예: 메타휴먼처럼
            # 이미 배치된 기존 스켈레톤) 팝핑 없이 정확한 오프셋을 유지하도록 한다.
            cmds.orientConstraint(ctrl, fk_jnts[i], maintainOffset=True)
            lock_hide(ctrl, attrs=("tx", "ty", "tz", "sx", "sy", "sz"))
            self.fk_ctrls.append(ctrl)
            self.all_ctrls.append(ctrl)
            fk_ctrls_this_limb.append(ctrl)
            prev_ctrl = ctrl

        # IK 솔버는 ik_jnts 위에서 직접 풀지 않고, 좌우 미러링 문제가 없는
        # "깨끗한" 프록시 체인을 하나 더 만들어 그 위에서 푼다 (자세한 이유는
        # _build_clean_ik_chain 참고 - 메타휴먼 오른쪽 다리가 뒤로 튀던
        # 버그의 실제 원인).
        ik_solve_jnts = self._build_clean_ik_chain(side, limb_type, ik_jnts, attach_parent)

        # ---------------- IK 컨트롤 ----------------
        end_name = f"{side}_{chain_cores[-1]}{IK_TAG}"
        ik_end_ctrl, ik_end_buf = create_control(end_name, shape=ik_shape,
                                                       radius=5 * self.radius_scale,
                                                       color_side=side, snap_to=ik_jnts[-1],
                                                       parent="CONTROLS_GRP")
        ik_handle_name = f"{side}_{limb_type}_ikHandle"
        ik_handle = cmds.ikHandle(name=ik_handle_name, startJoint=ik_solve_jnts[0],
                                   endEffector=ik_solve_jnts[-1], solver="ikRPsolver")[0]
        cmds.parent(ik_handle, ik_end_ctrl)
        cmds.setAttr(f"{ik_handle}.visibility", 0)
        cmds.orientConstraint(ik_end_ctrl, ik_solve_jnts[-1], maintainOffset=True)
        lock_hide(ik_end_ctrl, attrs=("sx", "sy", "sz"))

        # Pole Vector : 조인트 축 방향에 의존하지 않는 기하학적 계산
        # (캐릭터가 어느 방향을 보고 있든, 조인트 오리엔트 컨벤션이 무엇이든 동작).
        # 위치는 미러링 문제가 없는 ik_solve_jnts(클린 프록시) 기준으로 계산한다.
        start_pos = cmds.xform(ik_solve_jnts[0], q=True, worldSpace=True, translation=True)
        mid_pos = cmds.xform(ik_solve_jnts[1], q=True, worldSpace=True, translation=True)
        end_pos = cmds.xform(ik_solve_jnts[-1], q=True, worldSpace=True, translation=True)
        seg_len = self._dist(start_pos, mid_pos) + self._dist(mid_pos, end_pos)

        # 사람 모델은 대개 다리를 거의 완전히 편(무릎이 일자에 가까운) 채로
        # 서 있는 포즈로 임포트되는데, 이 경우 엉덩이-발목 거리가 팔다리의
        # 최대 리치(허벅지+정강이 길이 합)와 거의 같아져서 ikRPsolver 가
        # "완전히 뻗은" 특이점(singularity) 근처에서 풀게 된다. 이 지점은
        # 수치적으로 불안정해서(특히 메타휴먼처럼 좌우 조인트 오리엔트가
        # 180도 미러링되어 있는 쪽에서) 솔버가 목표에 전혀 도달하지 못하고
        # 발이 완전히 엉뚱한 곳으로 튀어버릴 수 있다(실제로 확인됨). IK
        # 컨트롤 목표 위치를 살짝(최대 리치의 99% 이내로) 안쪽으로 당겨서
        # 항상 눈에 띄지 않을 정도의 아주 작은 굽힘 여유를 남겨준다.
        orig_end_pos = end_pos
        end_pos = self._safe_ik_target(start_pos, end_pos, seg_len)
        if end_pos != orig_end_pos:
            cmds.xform(ik_end_buf, worldSpace=True, translation=end_pos)

        pv_pos, pv_dir = self._pole_vector_position(start_pos, mid_pos, end_pos,
                                                      seg_len * 0.6)
        pv_name = f"{side}_{limb_type}_pv"
        pv_ctrl, pv_buf = create_control(pv_name, shape=SHAPE_DIAMOND,
                                              radius=2.5 * self.radius_scale,
                                              color_side=side, parent="CONTROLS_GRP")
        cmds.xform(pv_buf, worldSpace=True, translation=pv_pos)
        cmds.poleVectorConstraint(pv_ctrl, ik_handle)
        lock_hide(pv_ctrl, attrs=("rx", "ry", "rz", "sx", "sy", "sz"))

        self.ik_ctrls.extend([ik_end_ctrl, pv_ctrl])
        self.all_ctrls.extend([ik_end_ctrl, pv_ctrl])

        # ---------------- 스위치 컨트롤 ----------------
        switch_name = f"{side}_{limb_type}_switch"
        switch_ctrl, switch_buf = create_control(switch_name, shape=SHAPE_CUBE,
                                                       radius=1.8 * self.radius_scale, color_side=side,
                                                       snap_to=bind_jnts[0], parent="CONTROLS_GRP")
        # 폴벡터와 같은 방향으로 살짝 띄워서 어깨/골반 컨트롤과 겹치지 않게 함
        nudge = seg_len * 0.15
        cmds.xform(switch_buf, relative=True,
                   translation=(pv_dir[0] * nudge, pv_dir[1] * nudge, pv_dir[2] * nudge))
        cmds.addAttr(switch_ctrl, longName="FK_IK", attributeType="float",
                     minValue=0, maxValue=1, defaultValue=0, keyable=True)
        lock_hide(switch_ctrl, attrs=("tx", "ty", "tz", "rx", "ry", "rz",
                                           "sx", "sy", "sz"))
        self.all_ctrls.append(switch_ctrl)
        self.switch_ctrls[f"{side}_{limb_type}"] = switch_ctrl

        rev = cmds.createNode("reverse", name=f"{side}_{limb_type}_switch_REV")
        cmds.connectAttr(f"{switch_ctrl}.FK_IK", f"{rev}.inputX")

        # 가시성 연결 (0=FK 보임, 1=IK 보임)
        for c in fk_ctrls_this_limb:
            grp = cmds.listRelatives(c, parent=True)[0]
            cmds.connectAttr(f"{rev}.outputX", f"{grp}.visibility")
        for c in (ik_end_ctrl, pv_ctrl):
            grp = cmds.listRelatives(c, parent=True)[0]
            cmds.connectAttr(f"{switch_ctrl}.FK_IK", f"{grp}.visibility")

        # ---------------- 블렌드 -> 바인드 조인트 ----------------
        for i in range(len(chain_cores)):
            bnode = cmds.createNode("blendColors", name=f"{side}_{limb_type}_{chain_cores[i]}_BLEND")
            cmds.connectAttr(f"{fk_jnts[i]}.rotate", f"{bnode}.color1")
            cmds.connectAttr(f"{ik_jnts[i]}.rotate", f"{bnode}.color2")
            cmds.connectAttr(f"{rev}.outputX", f"{bnode}.blender")
            cmds.connectAttr(f"{bnode}.output", f"{bind_jnts[i]}.rotate")

        limb_data = {
            "bind": bind_jnts, "fk_jnts": fk_jnts, "ik_jnts": ik_jnts,
            "ik_solve_jnts": ik_solve_jnts,
            "fk_ctrls": fk_ctrls_this_limb, "ik_ctrl": ik_end_ctrl,
            "pv_ctrl": pv_ctrl, "switch_ctrl": switch_ctrl, "ik_handle": ik_handle,
        }
        # match_and_switch() 에서 FK<->IK 전환 시 팝핑 없이 서로 자세를
        # 맞추는 데 사용하도록 저장해 둔다.
        self.limbs[f"{side}_{limb_type}"] = limb_data
        return limb_data

    # ------------------------------------------------------------------
    # 리버스 풋 (IK 다리의 발 롤)
    # ------------------------------------------------------------------
    def _build_reverse_foot(self, side):
        ankle = self.jnt.get(f"{side}_ankle")
        ball = self.jnt.get(f"{side}_ball")
        toe = self.jnt.get(f"{side}_toe")  # 없어도 됨 (예: 메타휴먼은 ball 이 마지막 발 조인트)
        if not (ankle and ball):
            return

        # 자가 진단 : ankle/ball 이름이 씬에서 유일하지 않으면(=이름이 같은
        # 조인트가 다른 계층에도 있으면) cmds.xform 등이 엉뚱한 노드를 조회할
        # 수 있다. 스크립트 에디터에 바로 남겨서 원인 파악이 쉽도록 한다.
        for label, resolved_jnt in (("ankle", ankle), ("ball", ball)):
            full_paths = cmds.ls(resolved_jnt, long=True) or []
            if len(full_paths) > 1:
                cmds.warning(
                    f"[AutoRig] {side} {label} 이름이 씬에서 유일하지 않습니다 "
                    f"({resolved_jnt} -> {full_paths}) : 컨트롤/피벗 위치가 엉뚱한 "
                    f"조인트를 기준으로 계산될 수 있습니다."
                )

        leg_key = f"{side}_leg"
        limb_data = self.limbs.get(leg_key)
        switch_ctrl = self.switch_ctrls.get(leg_key)
        ik_ctrl_name = f"{side}_ankle{IK_TAG}{CTRL_SUFFIX}"
        if not cmds.objExists(ik_ctrl_name):
            return

        # ankle IK 조인트 체인에서 ikHandle 을 만들 때 이미 hip-knee-ankle 까지만 사용했으므로
        # ball(/toe) 은 별도의 FK-style 회전으로 리버스 풋 피벗을 통해 굴린다.
        ball_ik = f"{side}_ball{IK_TAG}{JNT_SUFFIX}"
        if not cmds.objExists(ball_ik):
            ball_ik = cmds.duplicate(ball, name=ball_ik, parentOnly=True)[0]
            cmds.parent(ball_ik, f"{side}_ankle{IK_TAG}{JNT_SUFFIX}")

        toe_ik = None
        if toe:
            toe_ik = f"{side}_toe{IK_TAG}{JNT_SUFFIX}"
            if not cmds.objExists(toe_ik):
                toe_ik = cmds.duplicate(toe, name=toe_ik, parentOnly=True)[0]
                cmds.parent(toe_ik, ball_ik)

        # ---- heel(뒤꿈치) 위치를 기하학적으로 추정 ----
        # (가이드 로케이터 없이도 동작하도록 함 - 메타휴먼처럼 이미 배치된
        #  스켈레톤을 쓸 때는 GUIDE_ 로케이터가 아예 존재하지 않는다.)
        ankle_pos = self.rest_pos.get(f"{side}_ankle")
        ball_pos = self.rest_pos.get(f"{side}_ball")
        toe_tip_pos = self.rest_pos.get(f"{side}_toe") if toe else None
        if ankle_pos is None:
            ankle_pos = cmds.xform(ankle, q=True, worldSpace=True, translation=True)
        if ball_pos is None:
            ball_pos = cmds.xform(ball, q=True, worldSpace=True, translation=True)
        if toe and toe_tip_pos is None:
            toe_tip_pos = cmds.xform(toe, q=True, worldSpace=True, translation=True)

        # ---- 좌우 대칭 검증 (원본 스켈레톤 데이터 자체가 깨진 경우 자동 보정) ----
        # 메타휴먼처럼 이미 만들어진 스켈레톤을 그대로 가져다 쓰는 경우, 임포트/머지
        # 과정에서 특정 조인트 하나만 월드 포지션이 깨져 있는 사례가 실제로 있었다
        # (예: ball_r 의 Z 값만 수십 유닛 어긋남). 이런 조인트를 그대로 쓰면
        # ball_pivot_GRP 가 엉뚱한 곳에 생기고, 그 아래 매달린 leg IK 핸들이
        # IK 전환 시 그 위치로 끌려가서 "다리가 뒤로 휙 꺾인다" 는 증상이 난다.
        # 사람 캐릭터는 좌우 다리 길이가 거의 대칭이어야 하므로, 반대쪽 다리의
        # ankle-ball 거리와 비교해서 지금 이 쪽이 비정상적으로 다르면(2.5배 이상
        # 크거나 0.4배 이하로 작으면) ball_pos 가 오염된 것으로 보고 반대쪽의
        # ankle->ball 오프셋을 좌우로 미러링해서 재구성한다.
        opp_side = "R" if side == "L" else "L"
        opp_ankle_pos = self.rest_pos.get(f"{opp_side}_ankle")
        opp_ball_pos = self.rest_pos.get(f"{opp_side}_ball")
        if opp_ankle_pos is not None and opp_ball_pos is not None:
            this_len = self._dist(ankle_pos, ball_pos)
            opp_len = self._dist(opp_ankle_pos, opp_ball_pos)
            if opp_len > 1e-4 and (this_len > opp_len * 2.5 or this_len < opp_len * 0.4):
                mirrored_offset = (
                    -(opp_ball_pos[0] - opp_ankle_pos[0]),
                    (opp_ball_pos[1] - opp_ankle_pos[1]),
                    (opp_ball_pos[2] - opp_ankle_pos[2]),
                )
                corrected_ball_pos = (
                    ankle_pos[0] + mirrored_offset[0],
                    ankle_pos[1] + mirrored_offset[1],
                    ankle_pos[2] + mirrored_offset[2],
                )
                cmds.warning(
                    f"[AutoRig] {side} 리버스 풋 : '{ball}' 조인트의 원본 위치가 비정상적으로 "
                    f"보입니다 (ankle-ball 거리 {this_len:.2f} vs 반대쪽 다리 {opp_len:.2f}). "
                    f"원본 스켈레톤 파일 자체의 데이터 문제로 보이며, 반대쪽 다리를 좌우 "
                    f"미러링해서 자동 보정합니다 : {tuple(ball_pos)} -> {corrected_ball_pos}. "
                    f"'{ball}' 조인트의 위치를 원본 파일에서 직접 확인해 보시는 것을 권장합니다."
                )
                ball_pos = corrected_ball_pos
                self.rest_pos[f"{side}_ball"] = ball_pos
                # toe_tip 도 ball 기준으로 이어지는 값이라 같이 깨졌을 가능성이 높으므로
                # 반대쪽 ball->toe 오프셋을 마찬가지로 미러링해서 같이 보정한다.
                if toe_tip_pos is not None:
                    opp_toe_tip_pos = self.rest_pos.get(f"{opp_side}_toe")
                    if opp_toe_tip_pos is not None:
                        mirrored_toe_offset = (
                            -(opp_toe_tip_pos[0] - opp_ball_pos[0]),
                            (opp_toe_tip_pos[1] - opp_ball_pos[1]),
                            (opp_toe_tip_pos[2] - opp_ball_pos[2]),
                        )
                        toe_tip_pos = (
                            ball_pos[0] + mirrored_toe_offset[0],
                            ball_pos[1] + mirrored_toe_offset[1],
                            ball_pos[2] + mirrored_toe_offset[2],
                        )
                        self.rest_pos[f"{side}_toe"] = toe_tip_pos

        # ---- match_and_switch() 에서 재사용할 "발목 기준 상대 오프셋" 캐시 ----
        # heel/ball 피벗 그룹은 (아래에서) ik_ctrl 의 자식으로 붙는데, 그 로컬
        # 회전은 "지금(빌드 시점)" ik_ctrl 회전만 정확히 상쇄하도록 구워진다.
        # 나중에 match_and_switch() 가 다른 자세(다리를 다르게 포즈한 뒤 IK로
        # 전환하는 등)에서 ik_ctrl 을 다시 회전시키면, 그 구워진 상쇄값은 더
        # 이상 맞지 않게 되고, ik_ctrl 에서 ball_grp 까지의 지렛대 거리 때문에
        # 아주 작은 회전 차이도 ball_grp 를 크게 엉뚱한 위치로 밀어낸다(오른쪽
        # 다리가 IK 전환 시 뒤로 튀던 증상의 실제 원인 - 원래는 데이터가 깨진
        # 경우만 문제였지만, 사실 정상적인 데이터에서도 FK 자세를 바꾼 뒤
        # 전환하면 똑같이 재현되는 구조적인 문제였다). 그래서 ball/toe 의
        # 위치를 발목(fk_jnts[-1]) 기준 로컬 오프셋으로 따로 캐시해 두고,
        # match_and_switch() 가 호출될 때마다 "그 시점"의 실제 발목 월드
        # 매트릭스로 다시 계산해서 heel/ball(/toe) 피벗을 강제로 올바른
        # 위치로 되돌린다 (아래 _match_ik_to_current 참고).
        if limb_data is not None:
            ankle_ref = limb_data["fk_jnts"][-1]
            limb_data["ball_local_offset"] = self._world_offset_in_local_space(ankle_ref, ball_pos)
            limb_data["toe_local_offset"] = (
                self._world_offset_in_local_space(ankle_ref, toe_tip_pos)
                if toe_tip_pos else None
            )

        # 자가 진단 : 캐시된(빌드 시작 전) 위치와 지금 이 시점에 라이브로
        # 조회한 위치가 크게 다르면, 빌드 도중 뭔가가(라이브 커넥션 등)
        # 원본 바인드 조인트를 실제로 움직였다는 뜻이므로 스크립트 에디터에
        # 바로 경고를 남긴다 - 이 경고가 뜨는지 여부만으로 원인을 반으로
        # 좁힐 수 있다.
        live_ankle_pos = cmds.xform(ankle, q=True, worldSpace=True, translation=True)
        live_ball_pos = cmds.xform(ball, q=True, worldSpace=True, translation=True)
        if self._dist(ankle_pos, live_ankle_pos) > 0.5 or self._dist(ball_pos, live_ball_pos) > 0.5:
            cmds.warning(
                f"[AutoRig] {side} 리버스 풋 : 빌드 전 캐시된 위치와 지금 라이브로 "
                f"조회한 위치가 다릅니다 (빌드 도중 원본 조인트가 움직였다는 뜻). "
                f"ankle rest={ankle_pos} live={live_ankle_pos} / "
                f"ball rest={ball_pos} live={live_ball_pos} / "
                f"ankle full path={cmds.ls(ankle, long=True)} / "
                f"ball full path={cmds.ls(ball, long=True)}"
            )

        floor_y = min(ball_pos[1], (toe_tip_pos[1] if toe_tip_pos else ball_pos[1]), ankle_pos[1])
        forward = (ball_pos[0] - ankle_pos[0], 0.0, ball_pos[2] - ankle_pos[2])
        forward_len = math.sqrt(forward[0] ** 2 + forward[2] ** 2)
        if forward_len < 1e-4:
            forward = (0.0, 0.0, 1.0)
            forward_len = 1.0
        forward = (forward[0] / forward_len, 0.0, forward[2] / forward_len)
        heel_pos = (ankle_pos[0] - forward[0] * forward_len,
                    floor_y,
                    ankle_pos[2] - forward[2] * forward_len)

        # 피벗 그룹 : IK컨트롤 -> heel -> (toeTip) -> ball -> (toe, 발끝 들기)
        ik_ctrl = ik_ctrl_name
        heel_grp = cmds.group(empty=True, name=f"{side}_heel_pivot_GRP")
        ball_grp = cmds.group(empty=True, name=f"{side}_ball_pivot_GRP")
        cmds.xform(heel_grp, worldSpace=True, translation=heel_pos)
        cmds.xform(ball_grp, worldSpace=True, translation=ball_pos)

        toeTip_grp = None
        toe_grp = None
        if toe:
            toeTip_grp = cmds.group(empty=True, name=f"{side}_toeTip_pivot_GRP")
            toe_grp = cmds.group(empty=True, name=f"{side}_toe_pivot_GRP")
            cmds.xform(toeTip_grp, worldSpace=True, translation=toe_tip_pos)
            cmds.xform(toe_grp, worldSpace=True, translation=ball_pos)
            cmds.parent(toe_grp, ball_grp)
            cmds.parent(ball_grp, toeTip_grp)
            cmds.parent(toeTip_grp, heel_grp)
        else:
            cmds.parent(ball_grp, heel_grp)
        cmds.parent(heel_grp, ik_ctrl)

        # 기존 leg IK 핸들을 heel 체인이 아니라 ball_grp 아래로 옮겨서
        # 발목까지의 IK 는 ik_ctrl 을 그대로 따라가도록 유지한다.
        leg_ik_handle = f"{side}_leg_ikHandle"
        if cmds.objExists(leg_ik_handle):
            cmds.parent(leg_ik_handle, ball_grp)

        if toe:
            ball_toe_ik = cmds.ikHandle(name=f"{side}_ballToe_ikHandle", startJoint=ball_ik,
                                         endEffector=toe_ik, solver="ikSCsolver")[0]
            cmds.parent(ball_toe_ik, toe_grp)
            cmds.setAttr(f"{ball_toe_ik}.visibility", 0)

        # 발 롤 속성들을 IK 컨트롤에 추가
        roll_attrs = ["Roll", "Tilt"]
        if toe:
            roll_attrs += ["ToeTap", "HeelPivot", "ToePivot"]
        for attr in roll_attrs:
            cmds.addAttr(ik_ctrl, longName=attr, attributeType="float",
                         defaultValue=0, keyable=True)

        # Roll : 0보다 크면 ball 이 들리고(발끝으로 롤), 0보다 작으면 heel 이 들림
        cmds.setDrivenKeyframe(f"{ball_grp}.rotateX", currentDriver=f"{ik_ctrl}.Roll",
                               driverValue=0, value=0)
        cmds.setDrivenKeyframe(f"{ball_grp}.rotateX", currentDriver=f"{ik_ctrl}.Roll",
                               driverValue=45, value=45)
        cmds.setDrivenKeyframe(f"{heel_grp}.rotateX", currentDriver=f"{ik_ctrl}.Roll",
                               driverValue=0, value=0)
        cmds.setDrivenKeyframe(f"{heel_grp}.rotateX", currentDriver=f"{ik_ctrl}.Roll",
                               driverValue=-45, value=-45)
        cmds.connectAttr(f"{ik_ctrl}.Tilt", f"{ball_grp}.rotateZ")
        if toe:
            cmds.connectAttr(f"{ik_ctrl}.ToeTap", f"{toe_grp}.rotateX")
            cmds.connectAttr(f"{ik_ctrl}.HeelPivot", f"{heel_grp}.rotateY")
            cmds.connectAttr(f"{ik_ctrl}.ToePivot", f"{toeTip_grp}.rotateY")

        # ball(/toe) 바인드 조인트 회전은 IK 일 때 ball_ik(/toe_ik)를 그대로 따라가고
        # FK 일 때는 원래 회전을 유지하도록 스위치 처리
        if switch_ctrl:
            # _build_ikfk_limb 에서 만든 reverse 노드 재사용 : outputX = 1 - FK_IK
            # (FK_IK=0 일 때 blender=1 -> color1(정지/FK) 이 나오도록 동일한 규칙 유지)
            rev = f"{side}_leg_switch_REV"
            pairs = [(ball_ik, self.jnt[f"{side}_ball"], "ball")]
            if toe:
                pairs.append((toe_ik, self.jnt[f"{side}_toe"], "toe"))
            for src, dst, tag in pairs:
                bnode = cmds.createNode("blendColors", name=f"{side}_leg_{tag}_BLEND")
                cmds.setAttr(f"{bnode}.color1", 0, 0, 0, type="double3")
                cmds.connectAttr(f"{src}.rotate", f"{bnode}.color2")
                cmds.connectAttr(f"{rev}.outputX", f"{bnode}.blender")
                cmds.connectAttr(f"{bnode}.output", f"{dst}.rotate")

    # ------------------------------------------------------------------
    # 손가락 (FK + Curl 자동화)
    # ------------------------------------------------------------------
    def _build_fingers(self, side):
        # 손가락은 항상 바인드 손목 조인트를 부모로 두는 컨트롤 그룹으로 묶는다
        # (IK/FK 스위치와 무관하게 손목의 최종 바인드 트랜스폼을 그대로 따라감)
        wrist_jnt = self.jnt.get(f"{side}_wrist")
        if not wrist_jnt:
            return
        hand_grp = cmds.group(empty=True, name=f"{side}_fingers_GRP")
        cst = cmds.parentConstraint(wrist_jnt, hand_grp, maintainOffset=False)
        cmds.delete(cst)
        cmds.parent(hand_grp, "CONTROLS_GRP")
        cmds.parentConstraint(wrist_jnt, hand_grp, maintainOffset=True)
        cmds.scaleConstraint(wrist_jnt, hand_grp, maintainOffset=True)

        # 손 전체 컬 속성을 담을 손 옵션 컨트롤
        hand_opt, hand_opt_buf = create_control(f"{side}_handOptions",
                                                      shape=SHAPE_DIAMOND,
                                                      radius=1.5 * self.radius_scale,
                                                      color_side=side, snap_to=wrist_jnt,
                                                      parent=hand_grp)
        cmds.addAttr(hand_opt, longName="CurlAll", attributeType="float",
                     minValue=-1, maxValue=1, defaultValue=0, keyable=True)
        lock_hide(hand_opt, attrs=("tx", "ty", "tz", "rx", "ry", "rz",
                                        "sx", "sy", "sz"))
        self.all_ctrls.append(hand_opt)

        for finger in FINGER_NAMES:
            cmds.addAttr(hand_opt, longName=f"Curl_{finger.capitalize()}",
                         attributeType="float", minValue=-1, maxValue=1,
                         defaultValue=0, keyable=True)
            prev_ctrl = None
            # 00 = 메타카펄(옵션, 메타휴먼 등 기존 스켈레톤에만 존재), 01~03 = 손가락 마디.
            # 없는 인덱스는 건너뛴다 (엄지는 항상 00 없이 01~03 만 사용).
            joints_in_finger = [f"{side}_{finger}_{i:02d}" for i in (0, 1, 2, 3)]
            for idx, core in enumerate(joints_in_finger):
                jnt = self.jnt.get(core)
                if not jnt:
                    continue
                ctrl, buf = create_control(core, shape=SHAPE_CIRCLE,
                                                radius=1.0 * self.radius_scale,
                                                normal=(1, 0, 0), color_side=side,
                                                snap_to=jnt,
                                                parent=(prev_ctrl if prev_ctrl else hand_grp))
                cmds.parentConstraint(ctrl, jnt, maintainOffset=True)
                lock_hide(ctrl, attrs=("tx", "ty", "tz", "sx", "sy", "sz"))

                # 컬(curl) 자동화 : CurlAll + Curl_<finger> 를 더해서 rotateZ 로 구동
                add_node = cmds.createNode("plusMinusAverage",
                                           name=f"{core}_curl_ADD")
                cmds.connectAttr(f"{hand_opt}.CurlAll", f"{add_node}.input1D[0]")
                cmds.connectAttr(f"{hand_opt}.Curl_{finger.capitalize()}",
                                 f"{add_node}.input1D[1]")
                mult_node = cmds.createNode("multDoubleLinear",
                                            name=f"{core}_curl_MULT")
                cmds.connectAttr(f"{add_node}.output1D", f"{mult_node}.input1")
                cmds.setAttr(f"{mult_node}.input2", 60)  # 최대 굽힘 각도(도)
                # buffer 그룹의 rotateZ 에 연결 -> 컬 자동화 + 컨트롤 자체는
                # 애니메이터가 추가로 수동 회전 가능하도록 자유롭게 남겨둔다.
                cmds.connectAttr(f"{mult_node}.output", f"{buf}.rotateZ")

                self.fk_ctrls.append(ctrl)
                self.all_ctrls.append(ctrl)
                prev_ctrl = ctrl

    # ------------------------------------------------------------------
    # FK <-> IK 전환 시 팝핑 방지 (매치 후 스위치)
    # ------------------------------------------------------------------
    # 스위치 속성(FK_IK)만 바꾸면, 반대쪽 체인(IK 라면 IK 컨트롤들, FK 라면
    # FK 컨트롤들)은 마지막으로 빌드/조작됐던 자리에 그대로 있기 때문에,
    # 지금 화면에 보이는 자세와 전혀 다른 곳에 있을 수 있다 - 이게 스위치
    # 순간 캐릭터가 "팝"하며 다른 자세로 튀어 보이는 원인이다. 전환 직전에
    # 반대쪽 컨트롤을 지금 실제로 보이는 바인드 조인트 자세에 맞춰 먼저
    # 이동/회전시킨 뒤 스위치 값을 바꾸면, 전환 순간 자세가 유지된다.
    def match_and_switch(self, limb_key, target_value):
        data = self.limbs.get(limb_key)
        if not data:
            return
        if target_value >= 0.5:
            self._match_ik_to_current(data, limb_key)
        else:
            self._match_fk_to_current(data)
        cmds.setAttr(f"{data['switch_ctrl']}.FK_IK", target_value)

    def _match_fk_to_current(self, data):
        """지금 실제로 보이는 자세(현재 IK 로 구동 중이므로 ik_jnts 가 그
        값을 가지고 있음)를 FK 컨트롤들에 옮겨서, FK 로 전환해도 자세가
        바뀌지 않게 한다.

        주의: 매치 소스로 bind 조인트(data["bind"])를 쓰면 안 된다. bind
        조인트의 rotate 는 blendColors 를 통해 (전환하려는 대상인) FK
        컨트롤 쪽 체인에서 다시 흘러나오므로, "bind -> FK 컨트롤" 방향으로
        일시적 constraint 를 걸면 FK 컨트롤 -> fk_jnts -> blendColors ->
        bind 조인트 -> (지금 건 constraint) -> FK 컨트롤 로 이어지는 진짜
        사이클이 생겨 마야가 "Cycle on ..." 경고를 낸다. ik_jnts 는 FK
        컨트롤 체인과 전혀 연결되어 있지 않으므로(블렌드의 반대쪽 입력일
        뿐) 사이클 없이 안전하게 매치 소스로 쓸 수 있다."""
        for ctrl, ik_jnt in zip(data["fk_ctrls"], data["ik_jnts"]):
            cst = cmds.orientConstraint(ik_jnt, ctrl, maintainOffset=False)
            cmds.delete(cst)

    def _match_ik_to_current(self, data, limb_key=None):
        """지금 실제로 보이는 자세(현재 FK 로 구동 중이므로 fk_jnts 가 그
        값을 가지고 있음)에 맞춰 IK 엔드 컨트롤과 폴벡터 컨트롤을 다시
        배치해서, IK 로 전환해도 자세가 바뀌지 않게 한다. 폴벡터는 빌드
        시점이 아니라 "지금" 팔/다리가 굽혀진 방향으로 다시 기하학적으로
        계산한다.

        주의: 위 _match_fk_to_current 와 같은 이유로, 매치 소스로 bind
        조인트가 아니라 fk_jnts 를 써야 한다. IK 엔드 컨트롤은 orientConstraint
        로 ik_jnts 의 마지막 조인트를 구동하고, 그 값이 다시 blendColors 를
        거쳐 bind 조인트로 흘러가므로, bind 조인트를 소스로 쓰면
        "bind -> IK 컨트롤 -> ik_jnts -> blendColors -> bind" 사이클이 생긴다.
        fk_jnts 는 IK 쪽 체인과 연결되어 있지 않으므로 안전하다."""
        fk_jnts = data["fk_jnts"]
        last = fk_jnts[-1]
        cst = cmds.parentConstraint(last, data["ik_ctrl"], maintainOffset=False)
        cmds.delete(cst)

        start_pos = cmds.xform(fk_jnts[0], q=True, worldSpace=True, translation=True)
        mid_pos = cmds.xform(fk_jnts[1], q=True, worldSpace=True, translation=True)
        end_pos = cmds.xform(fk_jnts[-1], q=True, worldSpace=True, translation=True)
        seg_len = self._dist(start_pos, mid_pos) + self._dist(mid_pos, end_pos)

        # 다리를 거의 일자로 편 채 서 있는 등, 팔/다리가 거의 완전히 펴진
        # 자세일 때는 방금 위에서 맞춘 IK 컨트롤 위치가 ikRPsolver 의 "완전히
        # 뻗은" 특이점 근처에 놓이게 되어 솔버가 불안정해질 수 있다(오른쪽
        # 다리에서 발이 엉뚱한 곳으로 튀는 문제로 실제 확인됨). 살짝(최대
        # 리치의 99% 이내로) 안쪽으로 당겨서 항상 눈에 띄지 않을 정도의 작은
        # 굽힘 여유를 남겨준다.
        end_pos = self._safe_ik_target(start_pos, end_pos, seg_len)
        cmds.xform(data["ik_ctrl"], worldSpace=True, translation=end_pos)

        pv_pos, _pv_dir = self._pole_vector_position(start_pos, mid_pos, end_pos,
                                                       seg_len * 0.6)
        cmds.xform(data["pv_ctrl"], worldSpace=True, translation=pv_pos)

        # ---- 리버스 풋 피벗(heel/ball/toe) 위치 재보정 (다리 한정) ----
        # 방금 위에서 ik_ctrl 을 "지금 이 순간"의 FK 자세(빌드 때와 다른
        # 자세일 수 있음)에 맞춰 다시 회전시켰다. heel_grp/ball_grp 는
        # ik_ctrl 의 자식이고 그 로컬 회전은 빌드 시점 회전만 정확히
        # 상쇄하도록 구워져 있으므로, 그대로 두면 지렛대 효과로 엉뚱한
        # 위치로 밀려난다(발이 뒤로 튀는 증상의 실제 원인). _build_reverse_foot
        # 에서 발목(fk_jnts[-1]) 기준으로 캐시해 둔 상대 오프셋을, "지금"
        # 발목의 월드 매트릭스로 다시 계산해서 강제로 되돌린다.
        side = (limb_key or "").split("_")[0]
        ball_local_offset = data.get("ball_local_offset")
        if side and ball_local_offset is not None:
            ball_grp = f"{side}_ball_pivot_GRP"
            heel_grp = f"{side}_heel_pivot_GRP"
            toeTip_grp = f"{side}_toeTip_pivot_GRP"
            toe_grp = f"{side}_toe_pivot_GRP"
            if cmds.objExists(ball_grp):
                ball_pos_now = self._local_offset_to_world(last, ball_local_offset)
                toe_local_offset = data.get("toe_local_offset")
                toe_tip_pos_now = (
                    self._local_offset_to_world(last, toe_local_offset)
                    if toe_local_offset is not None else None
                )

                floor_y = min(ball_pos_now[1],
                               (toe_tip_pos_now[1] if toe_tip_pos_now else ball_pos_now[1]),
                               end_pos[1])
                forward = (ball_pos_now[0] - end_pos[0], 0.0, ball_pos_now[2] - end_pos[2])
                forward_len = math.sqrt(forward[0] ** 2 + forward[2] ** 2)
                if forward_len < 1e-4:
                    forward = (0.0, 0.0, 1.0)
                    forward_len = 1.0
                forward = (forward[0] / forward_len, 0.0, forward[2] / forward_len)
                heel_pos_now = (end_pos[0] - forward[0] * forward_len,
                                 floor_y,
                                 end_pos[2] - forward[2] * forward_len)

                # 부모 -> 자식 순서로(heel -> toeTip -> ball -> toe) 다시
                # 세팅한다 - 각 xform 호출은 절대 월드 좌표를 목표로 하므로
                # 부모를 먼저 옮겨서 자식이 같이 딸려가더라도 그 다음 호출이
                # 항상 다시 정확한 위치로 고정한다.
                if cmds.objExists(heel_grp):
                    cmds.xform(heel_grp, worldSpace=True, translation=heel_pos_now)
                if cmds.objExists(toeTip_grp) and toe_tip_pos_now is not None:
                    cmds.xform(toeTip_grp, worldSpace=True, translation=toe_tip_pos_now)
                cmds.xform(ball_grp, worldSpace=True, translation=ball_pos_now)
                if cmds.objExists(toe_grp):
                    cmds.xform(toe_grp, worldSpace=True, translation=ball_pos_now)

                # ---- leg_ikHandle 위치 직접 고정 (한 단계 더 남은 지렛대 문제) ----
                # ball_grp 의 "위치"는 방금 위에서 바로잡았지만, ball_grp 의
                # "로컬 회전"은 원래 항상 0 이고(Roll/Tilt 는 rotateX/rotateZ 로만
                # 들어옴) 그 월드 회전은 부모(heel_grp -> ... ) 에서 그대로
                # 물려받는다. heel_grp 의 로컬 회전은 여전히 "빌드 시점" ik_ctrl
                # 회전만 상쇄하도록 구워진 값 그대로이므로(회전까지 고치진
                # 않았음), ball_grp 도 지금은 회전이 0이 아니게 되어 있을 수
                # 있다. leg_ikHandle 은 ball_grp 의 자식이고 그 로컬 오프셋은
                # "ball_grp 회전이 0"이라는 가정하에 빌드 시점에 구워졌으므로,
                # 이 상태로 두면 발목 자체가 또 한 번 지렛대처럼 밀려난다(이번엔
                # 방향이 달라서 "앞으로" 튀는 것으로 나타남). Roll/Tilt 등 발
                # 롤 속성은 IK 로 막 전환하는 이 시점엔 항상 기본값(0)이므로,
                # leg_ikHandle 의 목표 위치는 결국 "지금 발목 위치"(end_pos)와
                # 같아야 정상이다 - ball_grp 회전 상태와 무관하게 절대 좌표로
                # 바로 강제해서 이 문제를 근본적으로 피한다.
                leg_ik_handle = f"{side}_leg_ikHandle"
                if cmds.objExists(leg_ik_handle):
                    cmds.xform(leg_ik_handle, worldSpace=True, translation=end_pos)

    # ------------------------------------------------------------------
    def get_all_controls(self):
        return list(dict.fromkeys(self.all_ctrls))


# SECTION: skin.py
# -*- coding: utf-8 -*-
"""
자동 스킨 바인딩 (Smooth Bind - Closest Distance)
----------------------------------------------------
전체 스케일이 바뀌어도 스킨 결과가 깨지지 않도록, 바인드는 항상
Global_CTRL 아래에 있는 최종 스켈레톤(바인드 조인트)에 대해서만 수행합니다.
"""



def auto_bind_skin(mesh, joints, max_influences=5, prune_below=0.005):
    """
    mesh    : 스킨을 씌울 메쉬 트랜스폼 이름
    joints  : 바인드에 사용할 조인트 이름 리스트 (SkeletonBuilder.get_bind_joints())
    """
    if not cmds.objExists(mesh):
        raise RuntimeError(f"메쉬를 찾을 수 없습니다: {mesh}")

    joints = [j for j in joints if cmds.objExists(j)]
    if not joints:
        raise RuntimeError("바인드할 조인트가 없습니다. 먼저 스켈레톤/리그를 생성하세요.")

    existing = cmds.ls(cmds.listHistory(mesh) or [], type="skinCluster")
    if existing:
        cmds.skinCluster(existing[0], edit=True, unbind=True)

    cmds.select(clear=True)
    skc = cmds.skinCluster(
        joints, mesh,
        toSelectedBones=True,
        bindMethod=0,          # Closest Distance
        skinMethod=0,          # Linear (Classic Linear)
        normalizeWeights=1,
        maximumInfluences=max_influences,
        obeyMaxInfluences=True,
        name=f"{mesh}_SKC",
    )[0]

    try:
        cmds.skinPercent(skc, mesh, pruneWeights=prune_below, normalize=True)
    except Exception:
        pass

    cmds.select(clear=True)
    return skc


def bind_selected(joints, prune_below=0.005):
    """현재 선택된 메쉬(들)에 대해 순차적으로 자동 바인딩."""
    meshes = []
    for sel in cmds.ls(selection=True, long=True) or []:
        shapes = cmds.listRelatives(sel, shapes=True, type="mesh") or []
        if shapes:
            meshes.append(sel)
    if not meshes:
        raise RuntimeError("메쉬를 먼저 선택하세요.")

    results = []
    for m in meshes:
        results.append(auto_bind_skin(m, joints, prune_below=prune_below))
    return results


# SECTION: ui.py
# -*- coding: utf-8 -*-
"""
Auto Rig Tool - Maya 네이티브 UI (cmds 기반, PySide 의존성 없음)
------------------------------------------------------------------
Maya 2022 ~ 2025+ 어떤 버전에서도(Qt 버전 상관없이) 그대로 동작하도록
maya.cmds 윈도우/레이아웃만 사용합니다.
"""



WINDOW_NAME = "autoRigToolWindow"

_state = {
    "guide_builder": None,
    "skeleton_builder": None,
    "rig_builder": None,
    "bind_joints": None,
    "mh_joint_map": None,
    "mh_spine_chain": None,
    "mh_skeleton_root": None,
}


def _log(msg):
    print(f"[AutoRig] {msg}")
    try:
        cmds.inViewMessage(amg=msg, pos="topCenter", fade=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 콜백들
# ---------------------------------------------------------------------------
def _cb_create_guides(*_):
    gb = GuideBuilder()
    gb.build_all()
    _state["guide_builder"] = gb
    _log("기본 T-포즈 가이드 생성 완료. 뷰포트에서 모델에 맞게 위치를 조정하세요.")


def _get_selected_mesh():
    for sel in cmds.ls(selection=True, long=True) or []:
        shapes = cmds.listRelatives(sel, shapes=True, type="mesh") or []
        if shapes:
            return sel
    return None


def _cb_auto_fit_guides(*_):
    mesh = _get_selected_mesh()
    if not mesh:
        cmds.warning("먼저 뷰포트/아웃라이너에서 사람 모델(메쉬)을 선택하세요.")
        return
    try:
        overrides, fp = compute_guide_positions(mesh)
    except RuntimeError as e:
        cmds.warning(str(e))
        return
    gb = GuideBuilder(position_overrides=overrides)
    gb.build_all()
    _state["guide_builder"] = gb
    _log(describe_fit(fp))
    print(f"[AutoRig] {describe_fit(fp)} "
          f"(width={fp['width']:.1f}, depth={fp['depth']:.1f})")


def _cb_mirror_guides(*_):
    gb = _state.get("guide_builder") or GuideBuilder()
    mirrored = gb.mirror_left_to_right()
    _log(f"{len(mirrored)}개 가이드를 오른쪽으로 미러했습니다.")


def _cb_delete_guides(*_):
    GuideBuilder.delete_all()
    _log("가이드를 삭제했습니다.")


def _cb_build_skeleton(*_):
    positions = GuideBuilder.get_world_positions()
    if not positions:
        cmds.warning("가이드가 없습니다. 먼저 '가이드 생성'을 실행하세요.")
        return
    sb = SkeletonBuilder()
    sb.build_from_guides(positions)
    _state["skeleton_builder"] = sb
    _state["bind_joints"] = sb.get_bind_joints()
    _log(f"스켈레톤 생성 완료 ({len(sb.joints)}개 조인트).")


def _cb_build_rig(*_):
    sb = _state.get("skeleton_builder")
    if not sb or not sb.joints:
        cmds.warning("먼저 '스켈레톤 생성'을 실행하세요.")
        return
    rb = RigBuilder(sb.joints)
    rb.build_all()
    _state["rig_builder"] = rb
    _log("컨트롤 리그(FK/IK) 생성 완료. Global_CTRL 로 전체 스케일 조정 가능합니다.")


# ---------------------------------------------------------------------------
# 메타휴먼 등, 이미 배치된 기존 스켈레톤을 사용하는 워크플로우
# ---------------------------------------------------------------------------
def _cb_scan_existing_skeleton(pelvis_field, report_field):
    pelvis_name = cmds.textField(pelvis_field, q=True, text=True).strip() or "pelvis"
    joint_map, spine_chain, skel_root, report = discover_skeleton(
        pelvis_name=pelvis_name)
    _state["mh_joint_map"] = joint_map
    _state["mh_spine_chain"] = spine_chain
    _state["mh_skeleton_root"] = skel_root
    text = format_report(report)
    if report_field and cmds.scrollField(report_field, exists=True):
        cmds.scrollField(report_field, edit=True, text=text)
    _log(f"스캔 완료 : 찾음 {len(report['found'])} / 누락 {len(report['missing'])}")
    print(f"[AutoRig]\n{text}")


def _cb_build_rig_from_existing(pelvis_field, report_field):
    if not _state.get("mh_joint_map"):
        _cb_scan_existing_skeleton(pelvis_field, report_field)
    joint_map = _state.get("mh_joint_map")
    if not joint_map or "root" not in joint_map:
        cmds.warning("pelvis(루트) 조인트를 찾지 못했습니다. 이름을 확인하고 "
                     "다시 스캔하세요.")
        return
    rb = RigBuilder(joint_map, spine_chain=_state.get("mh_spine_chain"),
                            existing_skeleton_root=_state.get("mh_skeleton_root"))
    rb.build_all()
    _state["rig_builder"] = rb
    _state["bind_joints"] = list(joint_map.values())
    _log("기존 스켈레톤 기반 컨트롤 리그(FK/IK) 생성 완료. "
         "기존 스킨 웨이트가 있었다면 그대로 유지됩니다.")


def _cb_bind_skin(*_):
    bind_joints = _state.get("bind_joints")
    if not bind_joints:
        cmds.warning("먼저 스켈레톤을 생성하거나(STEP1 탭) 기존 스켈레톤을 "
                     "스캔하세요(STEP1-B 탭).")
        return
    try:
        results = bind_selected(bind_joints)
        _log(f"{len(results)}개 메쉬에 스킨 바인딩 완료 (Closest Distance).")
    except RuntimeError as e:
        cmds.warning(str(e))


def _cb_cleanup_rig(*_):
    """
    이 툴이 씬에 만든 모든 흔적(FK/IK/Clean 조인트, blendColors/reverse/curl
    노드, ikHandle, RIG_GRP 계층 전체, 그리고 원본 바인드 조인트 위에 직접
    남아있는 관련 constraint)을 찾아서 지운다. 원본 바인드 스켈레톤 자체나
    스킨 클러스터는 절대 건드리지 않는다.

    왜 필요한가: RIG_GRP 를 지우는 것만으로는 충분하지 않다. FK/IK/Clean
    조인트는 원본 조인트의 "실제 부모" 밑에 만들어지므로(RIG_GRP 바깥),
    RIG_GRP 를 지워도 씬에 그대로 남는다. blendColors/reverse 같은 노드는
    애초에 계층 구조가 없는 디펜던시 그래프 노드라서 더더욱 RIG_GRP 삭제와
    무관하다. 스파인/쇄골/손가락처럼 컨트롤이 원본 바인드 조인트를 직접
    parentConstraint/orientConstraint 하는 경우도, 그 constraint 노드는
    바인드 조인트 자신의 자식으로 생기기 때문에 마찬가지로 RIG_GRP 삭제로는
    지워지지 않는다. 이런 흔적들이 "RIG_GRP 삭제 후 다시 빌드"를 반복할
    때마다 쌓이면서, 원본 바인드 조인트의 rotate/scale 값을 미묘하게
    오염시키고 다음 빌드 결과가 조금씩 어긋나는(예: 한쪽 발/피벗 위치가
    이상한 곳에 생기는) 원인이 된다.
    """
    rig_nodes = set()

    if cmds.objExists("RIG_GRP"):
        rig_nodes.add("RIG_GRP")
        rig_nodes.update(cmds.listRelatives("RIG_GRP", allDescendents=True) or [])

    for pattern, ntype in (
        ("*_FK_JNT", "joint"),
        ("*_IK_JNT", "joint"),
        ("*_IKClean_JNT", "joint"),
        ("*_BLEND", "blendColors"),
        ("*_switch_REV", "reverse"),
        ("*_curl_ADD", "plusMinusAverage"),
        ("*_curl_MULT", "multDoubleLinear"),
        ("*_ikHandle", "ikHandle"),
    ):
        rig_nodes.update(cmds.ls(pattern, type=ntype) or [])

    # ikHandle 에 딸린 ikEffector 도 같이 찾아서 지운다 (기본 이름이 자동
    # 생성되어 패턴 매칭이 안 되므로, 우리 ikHandle 에 실제로 연결된 것만
    # 찾아서 추가한다)
    for ikh in list(rig_nodes):
        if cmds.objExists(ikh) and cmds.objectType(ikh) == "ikHandle":
            effs = cmds.listConnections(ikh, type="ikEffector") or []
            rig_nodes.update(effs)

    if not rig_nodes:
        _log("삭제할 리그 흔적을 찾지 못했습니다 (이미 깨끗한 상태입니다).")
        return

    # 삭제되기 전에, 이 노드들이 원본 바인드 조인트의 rotate/scale 을
    # 구동하고 있었는지 찾아둔다 (삭제 후 바인드 포즈로 되돌리기 위해).
    affected_joints = set()
    for node in rig_nodes:
        if not cmds.objExists(node):
            continue
        downstream = cmds.listConnections(node, source=False, destination=True) or []
        for d in downstream:
            if d not in rig_nodes and cmds.objExists(d) and cmds.objectType(d) == "joint":
                affected_joints.add(d)

    # 바인드 조인트 위에 직접 만들어진 constraint (스파인/쇄골/손가락 FK 등)도
    # 찾는다 - 이런 constraint 는 조인트 자신의 자식으로 생기기 때문에
    # RIG_GRP 삭제로는 절대 지워지지 않는다.
    constraint_types = ("parentConstraint", "orientConstraint", "scaleConstraint",
                         "pointConstraint", "poleVectorConstraint", "aimConstraint")
    orphan_constraints = set()
    for ctype in constraint_types:
        for cst in (cmds.ls(type=ctype) or []):
            if cst in rig_nodes or not cmds.objExists(cst):
                continue
            sources = cmds.listConnections(cst, source=True, destination=False) or []
            if any(s in rig_nodes for s in sources):
                orphan_constraints.add(cst)
                for p in (cmds.listRelatives(cst, parent=True) or []):
                    if cmds.objExists(p) and cmds.objectType(p) == "joint":
                        affected_joints.add(p)

    # 실제 삭제 (constraint 를 먼저 지워야, RIG_GRP 삭제 시 "아직 연결되어
    # 있다"는 경고 없이 깔끔하게 지워진다)
    deleted = 0
    for node in list(orphan_constraints) + list(rig_nodes):
        if cmds.objExists(node):
            try:
                cmds.delete(node)
                deleted += 1
            except Exception:
                pass

    # 영향받은 원본 바인드 조인트를 바인드 포즈로 되돌린다 (local rotate=0,
    # scale=1). translate 는 조인트의 뼈 길이/부모 기준 오프셋이므로
    # 건드리지 않는다.
    reset_count = 0
    for jnt in affected_joints:
        if not cmds.objExists(jnt):
            continue
        try:
            for ax in "XYZ":
                r_attr = f"{jnt}.rotate{ax}"
                if cmds.objExists(r_attr) and cmds.getAttr(r_attr, settable=True):
                    cmds.setAttr(r_attr, 0)
                s_attr = f"{jnt}.scale{ax}"
                if cmds.objExists(s_attr) and cmds.getAttr(s_attr, settable=True):
                    cmds.setAttr(s_attr, 1)
            reset_count += 1
        except Exception:
            pass

    # rig_builder 는 이제 삭제된 노드들을 참조하는 stale 객체이므로 비운다.
    # (skeleton_builder 는 실제 바인드 스켈레톤을 들고 있는 객체라 건드리지
    # 않는다 - 그래야 "새 스켈레톤" 워크플로우에서 다시 스캔할 필요 없이
    # 바로 "컨트롤 리그 생성"을 눌러 재시도할 수 있다.)
    _state["rig_builder"] = None

    _log(f"리그 흔적 {deleted}개 삭제, 바인드 조인트 {reset_count}개를 바인드 "
         f"포즈로 복원했습니다. 원본 스켈레톤/스킨은 그대로입니다. 이제 "
         f"다시 컨트롤 리그를 생성하세요.")


def _cb_toggle_all_switch(value):
    rb = _state.get("rig_builder")
    if not rb:
        cmds.warning("먼저 리그를 생성하세요.")
        return
    # 단순히 FK_IK 속성만 바꾸면 반대쪽(IK<->FK) 컨트롤이 지금 자세와 다른
    # 곳에 있어서 전환 순간 캐릭터가 팝핑되므로, 전환 전에 항상 현재 자세로
    # 먼저 매치시키는 match_and_switch() 를 사용한다.
    if getattr(rb, "limbs", None):
        for limb_key in rb.limbs:
            rb.match_and_switch(limb_key, value)
    else:
        # 구버전 호환 : limbs 정보가 없으면(예전 리그) 예전처럼 단순 전환
        for switch_ctrl in rb.switch_ctrls.values():
            if cmds.objExists(f"{switch_ctrl}.FK_IK"):
                cmds.setAttr(f"{switch_ctrl}.FK_IK", value)
    _log(f"모든 팔/다리 스위치를 {'IK' if value else 'FK'} 로 전환했습니다 (자세 유지).")


def _cb_test_scale(value_field):
    rb = _state.get("rig_builder")
    if not rb or not cmds.objExists("Global_CTRL"):
        cmds.warning("먼저 리그를 생성하세요.")
        return
    val = cmds.floatField(value_field, q=True, value=True)
    cmds.setAttr("Global_CTRL.GlobalScale", val)
    _log(f"Global Scale = {val} 적용됨.")


# ---------------------------------------------------------------------------
# 윈도우
# ---------------------------------------------------------------------------
def _build_tab_new_skeleton(parent):
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=6,
                             columnAttach=("both", 8), parent=parent)

    cmds.text(label=" ", height=4)
    cmds.text(label="STEP 1. 가이드 배치", font="boldLabelFont", align="left")
    cmds.text(label="모델(메쉬)을 선택한 뒤 아래 버튼을 누르면 모델의 크기와\n"
                     "포즈(T-포즈/A-포즈/팔 붙임 등)를 자동으로 감지해서\n"
                     "가이드를 배치합니다. 이후 뷰포트에서 미세 조정하세요.",
              align="left", wordWrap=True, height=48)
    cmds.button(label="선택한 메쉬로 자동 배치 (크기+포즈 감지)", height=34,
                command=_cb_auto_fit_guides, backgroundColor=(0.35, 0.55, 0.35))

    cmds.text(label="또는 기본 T-포즈 가이드를 직접 배치하려면:", align="left")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 160), adjustableColumn=1)
    cmds.button(label="가이드 생성 (수동)", height=28, command=_cb_create_guides)
    cmds.button(label="왼쪽->오른쪽 미러", height=28, command=_cb_mirror_guides)
    cmds.setParent(col)
    cmds.button(label="가이드 삭제", height=22, command=_cb_delete_guides)

    cmds.separator(height=10, style="in")
    cmds.text(label="STEP 2. 스켈레톤 생성", font="boldLabelFont", align="left")
    cmds.text(label="가이드 위치를 기반으로 실제 바인드용 조인트를 만듭니다.",
              align="left")
    cmds.button(label="스켈레톤 생성", height=32, command=_cb_build_skeleton)

    cmds.separator(height=10, style="in")
    cmds.text(label="STEP 3. 컨트롤 리그 생성 (IK / FK)", font="boldLabelFont",
              align="left")
    cmds.text(label="FK, IK(폴벡터/리버스풋 포함), 손가락 컬, 전체 스케일 컨트롤이\n"
                     "자동으로 생성됩니다.", align="left")
    cmds.button(label="컨트롤 리그 생성", height=32, command=_cb_build_rig)

    cmds.separator(height=12, style="in")
    cmds.text(label="Tip: STEP 순서(1->2->3)대로 진행하세요. 가이드/조인트\n"
                     "위치가 마음에 안 들면 가이드를 옮긴 뒤 '스켈레톤 생성'\n"
                     "부터 다시 실행할 수 있습니다.",
              align="left", wordWrap=True, height=44)
    return col


def _build_tab_existing_skeleton(parent):
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=6,
                             columnAttach=("both", 8), parent=parent)

    cmds.text(label=" ", height=4)
    cmds.text(label="STEP 1-B. 기존 스켈레톤 사용 (메타휴먼 등)",
              font="boldLabelFont", align="left")
    cmds.text(label="메타휴먼처럼 모델에 이미 조인트가 배치/스킨되어 있는\n"
                     "경우, 새로 만들지 않고 그 조인트 위에 바로 IK/FK\n"
                     "컨트롤 리그를 얹습니다. 표준 UE5/메타휴먼 바디 네이밍\n"
                     "(pelvis, spine_01..., clavicle_l, upperarm_l, thigh_l 등)\n"
                     "을 기준으로 자동 스캔합니다.",
              align="left", wordWrap=True, height=96)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 180), adjustableColumn=2)
    cmds.text(label="Pelvis(루트) 조인트 이름", align="left")
    pelvis_field = cmds.textField(text="pelvis")
    cmds.setParent(col)

    report_field = cmds.scrollField(editable=False, wordWrap=True, height=110,
                                    text="아직 스캔하지 않았습니다.")

    cmds.button(label="스켈레톤 스캔 (미리 확인)", height=28,
                command=lambda *_: _cb_scan_existing_skeleton(pelvis_field, report_field))
    cmds.button(label="기존 스켈레톤으로 컨트롤 리그 생성", height=34,
                command=lambda *_: _cb_build_rig_from_existing(pelvis_field, report_field),
                backgroundColor=(0.35, 0.55, 0.35))

    cmds.separator(height=10, style="in")
    cmds.text(label="참고", font="boldLabelFont", align="left")
    cmds.text(label="- 좌/우 서픽스가 _l/_r 이 아니거나 pelvis 이름이 다르면\n"
                     "  auto_rig/metahuman_rig.py 의 DEFAULT_SIDE_SUFFIX,\n"
                     "  DEFAULT_PELVIS 를 상황에 맞게 수정하세요.\n"
                     "- 이미 스킨 바인딩된 메쉬라면 조인트 계층을 그대로\n"
                     "  두고 위에 IK/FK 만 얹으므로 기존 스킨은 유지됩니다.\n"
                     "- 스캔 결과에서 누락된 항목은 해당 부위 리그가\n"
                     "  생성되지 않으니 먼저 확인하세요.",
              align="left", wordWrap=True, height=110)
    return col


def show():
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    cmds.window(WINDOW_NAME, title="Auto Rig Tool (IK/FK + Auto Skin)",
                widthHeight=(360, 760), sizeable=True)
    main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=6,
                                     columnAttach=("both", 8))

    cmds.text(label=" ", height=2)
    cmds.text(label="리그를 다시 만들기 전에는 항상 먼저 아래 버튼을 누르세요",
              font="boldLabelFont", align="left")
    cmds.text(label="RIG_GRP 를 직접 지우는 것만으로는 FK/IK 듀플리케이트\n"
                     "조인트나 blendColors 같은 내부 노드가 씬에 남아 다음\n"
                     "빌드가 미묘하게 어긋날 수 있습니다. 이 버튼은 이 툴이\n"
                     "만든 모든 흔적을 찾아서 지우고, 원본 스켈레톤/스킨은\n"
                     "그대로 둡니다.",
              align="left", wordWrap=True, height=68)
    cmds.button(label="리그 완전 삭제 (다시 빌드하기 전 클릭)", height=34,
                command=_cb_cleanup_rig, backgroundColor=(0.55, 0.3, 0.3))
    cmds.separator(height=10, style="in")

    tabs = cmds.tabLayout(innerMarginWidth=5, innerMarginHeight=5)
    tab1 = _build_tab_new_skeleton(tabs)
    tab2 = _build_tab_existing_skeleton(tabs)
    cmds.tabLayout(tabs, edit=True, tabLabel=((tab1, "새 스켈레톤 생성"),
                                              (tab2, "기존 스켈레톤 사용")))
    cmds.setParent(main_layout)

    cmds.separator(height=10, style="in")
    cmds.text(label="공통 : IK/FK 스위치 & 전체 스케일 테스트", font="boldLabelFont",
              align="left")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 160), adjustableColumn=1)
    cmds.button(label="전체 FK 로 전환", height=24,
                command=lambda *_: _cb_toggle_all_switch(0))
    cmds.button(label="전체 IK 로 전환", height=24,
                command=lambda *_: _cb_toggle_all_switch(1))
    cmds.setParent(main_layout)

    cmds.text(label="Global Scale 테스트 (전체 스케일 안전성 확인)", align="left")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(220, 100), adjustableColumn=1)
    scale_field = cmds.floatField(value=1.0, minValue=0.01, maxValue=100)
    cmds.button(label="적용", command=lambda *_: _cb_test_scale(scale_field))
    cmds.setParent(main_layout)

    cmds.separator(height=10, style="in")
    cmds.text(label="공통 : 자동 스킨 바인딩", font="boldLabelFont", align="left")
    cmds.text(label="바인딩할 메쉬를 뷰포트/아웃라이너에서 선택한 뒤 실행하세요.\n"
                     "(Smooth Bind - Closest Distance. 메타휴먼처럼 이미 스킨된\n"
                     "메쉬라면 보통 다시 누를 필요는 없습니다.)",
              align="left", wordWrap=True, height=44)
    cmds.button(label="선택한 메쉬에 스킨 바인딩", height=32, command=_cb_bind_skin)

    cmds.showWindow(WINDOW_NAME)
    return WINDOW_NAME


show()