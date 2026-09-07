"""单实体音频选择状态，独立于树展开、搜索与 Qt 生命周期。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from .audio_scope import AudioScope, MappingNode

_UNDO_LIMIT = 50


@dataclass(frozen=True, slots=True)
class AudioSelectionState:
    """用目录标记或精确引用保存一次选择，不复制可用音频索引。"""

    all_selected: bool = False
    included: frozenset[Path] = frozenset()
    excluded: frozenset[Path] = frozenset()
    nodes: tuple[MappingNode, ...] = ()


class AudioSelection:
    """维护当前实体的路径级选择与有限撤销记录。"""

    def __init__(self) -> None:
        """初始化空选择，音频索引可在后台完成后补入。"""
        self.state = AudioSelectionState()
        self.available: frozenset[Path] = frozenset()
        self.revision = 0
        self._undo: list[AudioSelectionState] = []
        self._node_paths: dict[MappingNode, frozenset[Path]] = {}
        self._base_cache: tuple[int, frozenset[Path]] = (-1, frozenset())

    def reset(self) -> None:
        """切换实体时清除选择和撤销，不影响左侧任务对象。"""
        self.state = AudioSelectionState()
        self.available = frozenset()
        self._undo.clear()
        self._node_paths.clear()
        self.revision += 1

    def set_available(self, paths: Iterable[Path]) -> None:
        """替换已知可用索引，保留已确认的选择供执行时复核。"""
        self.available = frozenset(paths)
        self.revision += 1

    @property
    def has_selection(self) -> bool:
        """判断是否保存了目录或精确选择。"""
        return self.state.all_selected or bool(self.state.included) or bool(self.state.nodes and self.count)

    @property
    def can_undo(self) -> bool:
        """判断是否存在上一项用户选择动作。"""
        return bool(self._undo)

    @property
    def count(self) -> int:
        """返回当前已知选择数；目录最终数量由后台扫描决定。"""
        if self.state.all_selected:
            return len(self.available) - len(self.available & self.state.excluded)
        return len(self._base_paths() - self.state.excluded)

    def contains(self, path: Path) -> bool:
        """以物理路径判断选择，同一路径的事件引用共享状态。"""
        if self.state.all_selected:
            return path not in self.state.excluded
        return path in self._base_paths() and path not in self.state.excluded

    def count_paths(self, paths: frozenset[Path]) -> int:
        """对已解析节点范围计算选中数量，不展开或访问磁盘。"""
        if self.state.all_selected:
            return len(paths) - len(paths & self.state.excluded)
        return len((paths & self._base_paths()) - self.state.excluded)

    def _base_paths(self) -> frozenset[Path]:
        """按选择修订缓存节点成员并集，绘制时不反复合并万级路径。"""
        if self._base_cache[0] != self.revision:
            paths = self.state.included.union(*(self._node_paths[node] for node in self.state.nodes))
            self._base_cache = self.revision, paths
        return self._base_cache[1]

    def set_node(self, node: MappingNode, paths: Iterable[Path], checked: bool) -> None:
        """保留稳定节点引用，成员索引仅用于当前界面三态和计数。"""
        members = frozenset(paths) & self.available
        if not members:
            return
        if self.state.all_selected or not checked:
            self.set_paths(members, checked)
            return
        self._node_paths[node] = members
        nodes = tuple(dict.fromkeys((*self.state.nodes, node)))
        self._change(
            replace(
                self.state, nodes=nodes, included=self.state.included - members, excluded=self.state.excluded - members
            )
        )

    def select_all(self) -> None:
        """用一个目录标记全选当前实体，不遍历可用音频。"""
        self._change(AudioSelectionState(all_selected=True))

    def clear(self) -> None:
        """清空右侧音频选择，并作为一次可撤销动作。"""
        self._change(AudioSelectionState())

    def set_paths(self, paths: Iterable[Path], checked: bool) -> None:
        """修改节点下的可用音频，同一用户动作只保留一份撤销记录。"""
        members = frozenset(paths) & self.available
        if self.state.all_selected:
            excluded = self.state.excluded - members if checked else self.state.excluded | members
            self._change(AudioSelectionState(all_selected=True, excluded=excluded))
        else:
            included = (
                self.state.included | (members - self._base_paths()) if checked else self.state.included - members
            )
            excluded = self.state.excluded - members if checked else self.state.excluded | members
            self._change(replace(self.state, included=included, excluded=excluded))

    def undo(self) -> None:
        """恢复上一次选择修改，不撤销已产生的文件或任务。"""
        if self._undo:
            self.state = self._undo.pop()
            self.revision += 1

    def build_scopes(
        self, roots: tuple[Path, ...], *, prefixes: dict[Path, str] | None = None
    ) -> tuple[AudioScope, ...]:
        """按领域层提供的源目录生成紧凑请求，不传递全选路径数组。"""
        roots = tuple(Path(root).absolute() for root in roots)
        scopes: list[AudioScope] = []
        for root in roots:
            excluded = frozenset(
                path.relative_to(root).as_posix() for path in self.state.excluded if path.is_relative_to(root)
            )
            if self.state.all_selected:
                scopes.append(AudioScope(root, directories=(".",), excluded=excluded))
            else:
                files = tuple(
                    path.relative_to(root).as_posix() for path in self.state.included if path.is_relative_to(root)
                )
                nodes = tuple(
                    replace(node, prefix=(prefixes or {}).get(root, ""))
                    for node in self.state.nodes
                    if any(path.is_relative_to(root) for path in self._node_paths[node])
                )
                if files or nodes:
                    scopes.append(AudioScope(root, files=files, excluded=excluded, nodes=nodes))
        if any(not any(path.is_relative_to(root) for root in roots) for path in self.state.included):
            raise ValueError("所选音频不在当前实体目录内，请重新加载预览")
        return tuple(scopes)

    def _change(self, state: AudioSelectionState) -> None:
        if state == self.state:
            return
        self._undo.append(self.state)
        if len(self._undo) > _UNDO_LIMIT:
            self._undo.pop(0)
        self.state = state
        self.revision += 1
