import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
  Modal,
  Input,
  Form,
  Select,
  Empty,
  Dropdown,
  Typography,
  Spin,
  Segmented,
  Table,
  Tag,
  Space,
  Slider,
  Tooltip,
  Checkbox,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  MoreOutlined,
  ProjectOutlined,
  FilterOutlined,
  FullscreenOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  ScheduleOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useAppStore } from '../store';
import * as api from '../api/client';
import type { PlanBoard, PlanColumn, PlanTask, PlanTaskPriority, PlanTaskType } from '../api/types_plans';
import { ProfessionalGantt, type GanttViewMode } from '../components/ProfessionalGantt';

const { TextArea } = Input;
const STORAGE_KEY_PREFIX = 'nanobot_plans_';
const GANTT_GRANULARITY_KEY = 'nanobot_plans_gantt_granularity';
const QUERY_KEY = 'plans';

type GanttGranularity = 'minute' | 'hour' | 'day' | 'week' | 'month';

const GANTT_GRANULARITY_OPTIONS: { value: GanttGranularity; label: string }[] = [
  { value: 'minute', label: '5 分钟' },
  { value: 'hour', label: '小时' },
  { value: 'day', label: '天' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
];

function loadGanttGranularity(): GanttGranularity {
  try {
    const v = localStorage.getItem(GANTT_GRANULARITY_KEY);
    if (GANTT_GRANULARITY_OPTIONS.some((o) => o.value === v)) return v as GanttGranularity;
  } catch {
    // ignore
  }
  return 'day';
}

function saveGanttGranularity(g: GanttGranularity): void {
  try {
    localStorage.setItem(GANTT_GRANULARITY_KEY, g);
  } catch {
    // ignore
  }
}

const DEFAULT_COLUMNS: PlanColumn[] = [
  { id: 'col-backlog', title: '待办', order: 0 },
  { id: 'col-progress', title: '进行中', order: 1 },
  { id: 'col-done', title: '已完成', order: 2 },
];

const COLUMN_STYLES: Record<string, { accent: string; bg: string; border: string; dot: string }> = {
  'col-backlog': {
    accent: 'text-slate-600 dark:text-slate-400',
    bg: 'bg-slate-50/80 dark:bg-slate-900/30',
    border: 'border-slate-200/80 dark:border-slate-700/60',
    dot: 'bg-slate-400',
  },
  'col-progress': {
    accent: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50/60 dark:bg-amber-950/20',
    border: 'border-amber-200/60 dark:border-amber-800/40',
    dot: 'bg-blue-500',
  },
  'col-done': {
    accent: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50/60 dark:bg-emerald-950/20',
    border: 'border-emerald-200/60 dark:border-emerald-800/40',
    dot: 'bg-emerald-500',
  },
};

function getColumnStyle(columnId: string) {
  const base = COLUMN_STYLES[columnId] ?? COLUMN_STYLES['col-backlog'];
  return { ...base, dot: base.dot ?? 'bg-gray-400' };
}

const PRIORITY_OPTIONS: { value: PlanTaskPriority; label: string; color: string; dot: string }[] = [
  { value: 'high', label: '高', color: 'red', dot: 'bg-red-500' },
  { value: 'medium', label: '中', color: 'orange', dot: 'bg-orange-500' },
  { value: 'low', label: '低', color: 'default', dot: 'bg-emerald-400' },
];

function createDefaultBoard(): PlanBoard {
  return {
    id: 'board-default',
    name: '默认看板',
    columns: DEFAULT_COLUMNS,
    tasks: [],
  };
}

function loadFromStorage(botId: string): PlanBoard {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PREFIX + botId);
    if (!raw) return createDefaultBoard();
    const parsed = JSON.parse(raw) as PlanBoard;
    if (!parsed.columns?.length) parsed.columns = DEFAULT_COLUMNS;
    if (!parsed.tasks) parsed.tasks = [];
    return parsed;
  } catch {
    return createDefaultBoard();
  }
}

function saveToStorage(botId: string, board: PlanBoard): void {
  try {
    localStorage.setItem(STORAGE_KEY_PREFIX + botId, JSON.stringify(board));
  } catch {
    // ignore
  }
}

function generateId(): string {
  return 'task-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 9);
}

function getColumnTitle(columns: PlanColumn[], columnId: string): string {
  return columns.find((c) => c.id === columnId)?.title ?? columnId;
}

function getPriorityLabel(priority?: PlanTaskPriority): string {
  return PRIORITY_OPTIONS.find((p) => p.value === priority)?.label ?? '-';
}

function isOverdue(dueDate?: string): boolean {
  if (!dueDate) return false;
  return new Date(dueDate) < new Date();
}

/** 将 ISO 字符串转为 datetime-local 输入值（本地时间，精确到秒） */
function toDateTimeLocal(iso?: string): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${day}T${h}:${min}:${s}`;
}

/** 格式化日期时间显示（精确到秒） */
function formatDateTime(d?: string): string {
  if (!d) return '-';
  return new Date(d).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** 获取任务的甘特图时间范围：start 用 startDate 或 createdAt，end 用 dueDate 或 start+1 天 */
function getGanttRange(task: PlanTask): { start: Date; end: Date } {
  const start = task.startDate
    ? new Date(task.startDate)
    : new Date(task.createdAt);
  const end = task.dueDate ? new Date(task.dueDate) : new Date(start.getTime() + 24 * 60 * 60 * 1000);
  return { start, end };
}

interface GanttTaskBarProps {
  task: PlanTask;
  left: number;
  width: number;
  start: Date;
  end: Date;
  rangeStart: Date;
  totalMs: number;
  timelineWidth: number;
  isSelected?: boolean;
  onEdit: (task: PlanTask) => void;
  onUpdateDates: (taskId: string, startDate: string, dueDate: string) => void;
}

function formatGanttDate(d: Date): string {
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function GanttTaskBar({
  task,
  left,
  width,
  start,
  end,
  rangeStart,
  totalMs,
  timelineWidth,
  isSelected,
  onEdit,
  onUpdateDates,
}: GanttTaskBarProps) {
  const [dragState, setDragState] = useState<{ left: number; width: number } | null>(null);
  const dragStartRef = useRef<{ x: number; left: number; width: number } | null>(null);
  const hasMovedRef = useRef(false);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      hasMovedRef.current = false;
      dragStartRef.current = { x: e.clientX, left, width };
      setDragState({ left, width });

      const handleMouseMove = (ev: MouseEvent) => {
        const start = dragStartRef.current;
        if (!start) return;
        hasMovedRef.current = true;
        const deltaX = ev.clientX - start.x;
        const deltaPercent = (deltaX / timelineWidth) * 100;
        const newLeft = Math.max(0, Math.min(100 - start.width, start.left + deltaPercent));
        setDragState({ left: newLeft, width: start.width });
      };

      const handleMouseUp = (ev: MouseEvent) => {
        const start = dragStartRef.current;
        if (!start) return;
        dragStartRef.current = null;
        setDragState(null);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);

        if (!hasMovedRef.current) {
          onEdit(task);
          return;
        }
        const deltaX = ev.clientX - start.x;
        const deltaPercent = (deltaX / timelineWidth) * 100;
        const newLeft = Math.max(0, Math.min(100 - start.width, start.left + deltaPercent));
        const newStartMs = rangeStart.getTime() + (newLeft / 100) * totalMs;
        const newEndMs = rangeStart.getTime() + ((newLeft + start.width) / 100) * totalMs;
        onUpdateDates(task.id, new Date(newStartMs).toISOString(), new Date(newEndMs).toISOString());
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [left, width, rangeStart, totalMs, timelineWidth, task, onEdit, onUpdateDates]
  );

  const displayLeft = dragState?.left ?? left;
  const displayWidth = dragState?.width ?? width;

  const dateLabel = `${formatGanttDate(start)} - ${formatGanttDate(end)}`;
  const showDates = displayWidth > 15;

  const barColor = isSelected
    ? 'bg-blue-500 dark:bg-blue-600 shadow-md'
    : 'bg-slate-600 dark:bg-slate-500 hover:bg-slate-500 dark:hover:bg-slate-400';
  const ringColor = isSelected ? 'ring-blue-400/50' : 'ring-slate-400/30';

  return (
    <div
      className={`absolute top-1/2 -translate-y-1/2 h-5 rounded-md cursor-grab active:cursor-grabbing transition-all select-none ${barColor} ${dragState ? `z-10 ring-2 ${ringColor} shadow-lg scale-[1.02]` : 'shadow-sm'}`}
      style={{
        left: `${displayLeft}%`,
        width: `${displayWidth}%`,
        minWidth: 24,
      }}
      title={`${task.title} · ${dateLabel}\n拖动可调整时间`}
      onMouseDown={handleMouseDown}
    >
      <span className="absolute inset-0 flex items-center justify-between px-2 gap-1 pointer-events-none overflow-hidden">
        <span className="text-[11px] font-medium text-white truncate drop-shadow-sm">{task.title}</span>
        {showDates && (
          <span className="text-[9px] text-white/80 shrink-0 whitespace-nowrap tabular-nums">{dateLabel}</span>
        )}
      </span>
    </div>
  );
}


interface GanttViewProps {
  tasks: PlanTask[];
  granularity: GanttGranularity;
  selectedTaskId?: string | null;
  embedded?: boolean;
  onEdit: (task: PlanTask) => void;
  onDelete: (taskId: string) => void;
  onUpdateDates: (taskId: string, startDate: string, dueDate: string) => void;
  getColumnTitle: (columnId: string) => string;
  priorityOptions: { value: PlanTaskPriority; label: string; color: string; dot?: string }[];
}

function startOfWeek(d: Date): Date {
  const r = new Date(d);
  const day = r.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  r.setDate(r.getDate() + diff);
  r.setHours(0, 0, 0, 0);
  return r;
}

function getISOWeekNumber(d: Date): number {
  const target = new Date(d);
  const dayNr = (target.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.getTime();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  return 1 + Math.ceil((firstThursday - target.getTime()) / 604800000);
}

function startOfMonth(d: Date): Date {
  const r = new Date(d);
  r.setDate(1);
  r.setHours(0, 0, 0, 0);
  return r;
}

function endOfMonth(d: Date): Date {
  const r = new Date(d);
  r.setMonth(r.getMonth() + 1);
  r.setDate(0);
  r.setHours(23, 59, 59, 999);
  return r;
}

function startOfHour(d: Date): Date {
  const r = new Date(d);
  r.setMinutes(0, 0, 0);
  return r;
}

function startOfMinute(d: Date): Date {
  const r = new Date(d);
  r.setSeconds(0, 0);
  return r;
}

function isWeekend(d: Date): boolean {
  const day = d.getDay();
  return day === 0 || day === 6;
}

function GanttView({
  tasks,
  granularity,
  selectedTaskId,
  embedded,
  onEdit,
  onDelete,
  onUpdateDates,
  getColumnTitle,
  priorityOptions,
}: GanttViewProps) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let rangeStart: Date;
  let rangeEnd: Date;

  const MS_HOUR = 60 * 60 * 1000;
  const MS_DAY = 24 * MS_HOUR;

  if (tasks.length > 0) {
    const minStart = Math.min(...tasks.map((t) => getGanttRange(t).start.getTime()));
    const maxEnd = Math.max(...tasks.map((t) => getGanttRange(t).end.getTime()));
    const rawStart = new Date(Math.min(minStart, today.getTime()));
    const rawEnd = new Date(Math.max(maxEnd, today.getTime() + 28 * MS_DAY));

    if (granularity === 'minute') {
      rangeStart = startOfMinute(rawStart);
      rangeStart.setMinutes(Math.floor(rangeStart.getMinutes() / 5) * 5);
      rangeStart.setTime(rangeStart.getTime() - 30 * 60 * 1000);
      rangeEnd = startOfMinute(rawEnd);
      rangeEnd.setMinutes(Math.ceil(rangeEnd.getMinutes() / 5) * 5);
      rangeEnd.setTime(rangeEnd.getTime() + 30 * 60 * 1000);
    } else if (granularity === 'hour') {
      rangeStart = startOfHour(rawStart);
      rangeStart.setTime(rangeStart.getTime() - 6 * MS_HOUR);
      rangeEnd = startOfHour(rawEnd);
      rangeEnd.setTime(rangeEnd.getTime() + 6 * MS_HOUR);
      const totalHours = (rangeEnd.getTime() - rangeStart.getTime()) / MS_HOUR;
      if (totalHours > 48) {
        rangeEnd.setTime(rangeStart.getTime() + 48 * MS_HOUR);
      }
    } else if (granularity === 'day') {
      rangeStart = new Date(rawStart);
      rangeEnd = new Date(rawEnd);
      rangeStart.setDate(rangeStart.getDate() - 7);
      rangeEnd.setDate(rangeEnd.getDate() + 14);
    } else if (granularity === 'week') {
      rangeStart = startOfWeek(rawStart);
      rangeStart.setDate(rangeStart.getDate() - 7);
      const endWeek = startOfWeek(rawEnd);
      rangeEnd = new Date(endWeek);
      rangeEnd.setDate(rangeEnd.getDate() + 14);
    } else {
      rangeStart = startOfMonth(rawStart);
      rangeStart.setMonth(rangeStart.getMonth() - 1);
      rangeEnd = endOfMonth(rawEnd);
      rangeEnd.setMonth(rangeEnd.getMonth() + 2);
    }
  } else {
    rangeStart = new Date(today);
    rangeEnd = new Date(today);
    if (granularity === 'minute') {
      const now = new Date();
      rangeStart = new Date(now);
      rangeStart.setMinutes(Math.floor(rangeStart.getMinutes() / 5) * 5, 0, 0);
      rangeStart.setTime(rangeStart.getTime() - 30 * 60 * 1000);
      rangeEnd = new Date(rangeStart.getTime() + 60 * 60 * 1000);
    } else if (granularity === 'hour') {
      rangeStart = startOfHour(rangeStart);
      rangeStart.setTime(rangeStart.getTime() - 12 * MS_HOUR);
      rangeEnd.setTime(rangeEnd.getTime() + 12 * MS_HOUR);
    } else if (granularity === 'day') {
      rangeStart.setDate(rangeStart.getDate() - 7);
      rangeEnd.setDate(rangeEnd.getDate() + 28);
    } else if (granularity === 'week') {
      rangeStart = startOfWeek(rangeStart);
      rangeStart.setDate(rangeStart.getDate() - 7);
      rangeEnd.setDate(rangeEnd.getDate() + 35);
    } else {
      rangeStart = startOfMonth(rangeStart);
      rangeStart.setMonth(rangeStart.getMonth() - 1);
      rangeEnd.setMonth(rangeEnd.getMonth() + 2);
    }
  }

  const totalMs = rangeEnd.getTime() - rangeStart.getTime();
  const cellWidth =
    granularity === 'minute' ? 32 : granularity === 'hour' ? 40 : granularity === 'day' ? 36 : granularity === 'week' ? 72 : 96;

  const toPercent = (d: Date) => {
    const ms = d.getTime() - rangeStart.getTime();
    return Math.max(0, Math.min(100, (ms / totalMs) * 100));
  };

  const ganttTasks = tasks
    .map((t) => {
      const { start, end } = getGanttRange(t);
      return {
        task: t,
        start,
        end,
        left: toPercent(start),
        width: Math.max(2, toPercent(end) - toPercent(start)),
      };
    })
    .sort((a, b) => a.start.getTime() - b.start.getTime());

  const timeSlots: { label: string; date: Date; showLabel: boolean; isDayStart: boolean; isWeekend?: boolean }[] = [];
  if (granularity === 'minute') {
    for (let d = new Date(startOfMinute(rangeStart)); d <= rangeEnd; d.setMinutes(d.getMinutes() + 5)) {
      const h = d.getHours();
      const min = d.getMinutes();
      const isDayStart = h === 0 && min === 0;
      timeSlots.push({
        label: isDayStart
          ? `${d.getMonth() + 1}/${d.getDate()}`
          : `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`,
        date: new Date(d),
        showLabel: isDayStart || min % 15 === 0,
        isDayStart,
      });
    }
  } else if (granularity === 'hour') {
    for (let d = new Date(startOfHour(rangeStart)); d <= rangeEnd; d.setTime(d.getTime() + MS_HOUR)) {
      const h = d.getHours();
      const isDayStart = h === 0;
      timeSlots.push({
        label: isDayStart
          ? `${d.getMonth() + 1}/${d.getDate()}`
          : `${String(h).padStart(2, '0')}:00`,
        date: new Date(d),
        showLabel: isDayStart || h % 3 === 0,
        isDayStart,
      });
    }
  } else if (granularity === 'day') {
    for (let d = new Date(rangeStart); d <= rangeEnd; d.setDate(d.getDate() + 1)) {
      const slotDate = new Date(d);
      timeSlots.push({
        label: `${d.getMonth() + 1}/${d.getDate()}`,
        date: slotDate,
        showLabel: true,
        isDayStart: true,
        isWeekend: isWeekend(slotDate),
      });
    }
  } else if (granularity === 'week') {
    for (let d = new Date(startOfWeek(rangeStart)); d <= rangeEnd; d.setDate(d.getDate() + 7)) {
      timeSlots.push({
        label: `${d.getMonth() + 1}/${d.getDate()}`,
        date: new Date(d),
        showLabel: true,
        isDayStart: true,
      });
    }
  } else {
    for (let d = new Date(startOfMonth(rangeStart)); d <= rangeEnd; d.setMonth(d.getMonth() + 1)) {
      const y = d.getFullYear();
      const m = d.getMonth();
      timeSlots.push({
        label: `${y}-${String(m + 1).padStart(2, '0')}`,
        date: new Date(y, m, 1),
        showLabel: true,
        isDayStart: true,
      });
    }
  }

  const timelineWidth = timeSlots.length * cellWidth;

  const todayPercent = toPercent(new Date());

  const monthGroups: { label: string; span: number }[] = [];
  if (granularity === 'day' && timeSlots.length > 0) {
    let i = 0;
    while (i < timeSlots.length) {
      const d = timeSlots[i].date;
      const monthKey = `${d.getFullYear()}-${d.getMonth()}`;
      let count = 0;
      while (i + count < timeSlots.length) {
        const t = timeSlots[i + count].date;
        if (`${t.getFullYear()}-${t.getMonth()}` !== monthKey) break;
        count++;
      }
      monthGroups.push({ label: `${d.getMonth() + 1}月`, span: count });
      i += count;
    }
  } else if (granularity === 'week' && timeSlots.length > 0) {
    let i = 0;
    while (i < timeSlots.length) {
      const d = timeSlots[i].date;
      const monthKey = `${d.getFullYear()}-${d.getMonth()}`;
      let count = 0;
      while (i + count < timeSlots.length) {
        const t = timeSlots[i + count].date;
        if (`${t.getFullYear()}-${t.getMonth()}` !== monthKey) break;
        count++;
      }
      monthGroups.push({ label: `${d.getMonth() + 1}月`, span: count });
      i += count;
    }
  } else if (granularity === 'month' && timeSlots.length > 0) {
    timeSlots.forEach((s) => monthGroups.push({ label: s.label, span: 1 }));
  }

  const hasTwoRowHeader = (granularity === 'day' || granularity === 'week') && monthGroups.length > 0;

  if (tasks.length === 0) {
    return (
      <div className={embedded ? 'flex-1 flex flex-col items-center justify-center py-20 bg-gray-50/50 dark:bg-gray-800/30 rounded-r-2xl' : ''}>
        <Card className={embedded ? 'border-0 shadow-none bg-transparent' : 'rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm'}>
          <div className="py-20 flex flex-col items-center justify-center gap-2 text-gray-400 dark:text-gray-500">
            <ProjectOutlined style={{ fontSize: 48 }} />
            <p>暂无任务，创建任务后可在此查看甘特图</p>
            <p className="text-xs">请为任务设置开始日期和截止日期以获得更好的展示效果</p>
          </div>
        </Card>
      </div>
    );
  }

  const content = (
      <div className="overflow-x-auto">
        <div className="min-w-max">
          {/* 表头：时间轴 */}
          <div className="flex flex-col border-b border-gray-200 dark:border-gray-600">
            {hasTwoRowHeader ? (
              <>
                <div className="flex">
                  {!embedded && (
                    <div className="w-52 shrink-0 sticky left-0 z-10 px-3 py-1.5 text-[11px] font-semibold text-gray-600 dark:text-gray-400 border-r border-b border-gray-200 dark:border-gray-600 bg-gray-50/90 dark:bg-gray-800/80">
                      任务
                    </div>
                  )}
                  <div className="flex" style={{ width: timelineWidth }}>
                    {monthGroups.map((g, i) => (
                      <div
                        key={i}
                        className="shrink-0 py-1 text-center text-[11px] font-medium text-gray-600 dark:text-gray-400 border-l border-gray-200 dark:border-gray-600 bg-gray-50/70 dark:bg-gray-800/60 first:border-l-0"
                        style={{ width: g.span * cellWidth, minWidth: g.span * cellWidth }}
                      >
                        {g.label}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex">
                  {!embedded && (
                    <div className="w-52 shrink-0 sticky left-0 z-10 px-3 py-1.5 text-xs text-gray-500 dark:text-gray-500 border-r border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)] dark:shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]" />
                  )}
                  <div className="flex" style={{ width: timelineWidth }}>
                    {timeSlots.map((slot, i) => {
                      const now = new Date();
                      const isCurrent =
                        granularity === 'day'
                          ? slot.date.toDateString() === now.toDateString()
                          : slot.date <= now && new Date(slot.date.getTime() + 7 * MS_DAY) > now;
                      const label =
                        granularity === 'day'
                          ? `${slot.date.getDate()}`
                          : `${getISOWeekNumber(slot.date)}`;
                      const weekendBg = slot.isWeekend ? 'bg-gray-100/60 dark:bg-gray-800/40' : '';
                      return (
                        <div
                          key={i}
                          className={`shrink-0 py-1 text-center text-[11px] tabular-nums ${
                            slot.isDayStart ? 'border-l border-gray-200 dark:border-gray-600' : ''
                          } ${weekendBg} ${isCurrent ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 font-semibold' : !slot.isWeekend ? 'bg-white dark:bg-gray-800/40 text-gray-600 dark:text-gray-400' : 'text-gray-400 dark:text-gray-500'}`}
                          style={{ width: cellWidth, minWidth: cellWidth }}
                        >
                          {label}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex">
                {!embedded && (
                  <div className="w-52 shrink-0 sticky left-0 z-10 px-3 py-2.5 font-medium text-gray-600 dark:text-gray-400 border-r border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)] dark:shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">
                    任务
                  </div>
                )}
                <div className="flex relative" style={{ width: timelineWidth }}>
                  {timeSlots.map((slot, i) => {
                    const now = new Date();
                    const isCurrent =
                      granularity === 'minute'
                        ? Math.floor(slot.date.getTime() / (5 * 60 * 1000)) ===
                          Math.floor(startOfMinute(now).getTime() / (5 * 60 * 1000))
                        : granularity === 'hour'
                          ? slot.date.getTime() === startOfHour(now).getTime()
                          : granularity === 'month' &&
                            slot.date.getMonth() === now.getMonth() &&
                            slot.date.getFullYear() === now.getFullYear();
                    return (
                      <div
                        key={i}
                        className={`shrink-0 py-1.5 text-center text-[11px] tabular-nums ${
                          slot.isDayStart ? 'border-l border-gray-200 dark:border-gray-600' : ''
                        } ${isCurrent ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 font-semibold' : 'bg-gray-50/50 dark:bg-gray-800/40 text-gray-600 dark:text-gray-400'}`}
                        style={{ width: cellWidth, minWidth: cellWidth }}
                      >
                        {slot.showLabel && slot.label}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          {/* 任务行 */}
          <div className="relative">
            {/* 今日指示线：定位到时间轴区域（embedded 时无左侧任务列） */}
            {todayPercent >= 0 && todayPercent <= 100 && (
              <div
                className="absolute top-0 bottom-0 w-0 border-l-2 border-dashed border-amber-500/80 dark:border-amber-400/80 z-20 pointer-events-none"
                style={{ left: embedded ? `${(timelineWidth * todayPercent) / 100}px` : `calc(13rem + ${(timelineWidth * todayPercent) / 100}px)` }}
              />
            )}
            {ganttTasks.map(({ task, left, width, start, end }) => {
            const priorityOpt = priorityOptions.find((p) => p.value === task.priority);
            const isSelected = selectedTaskId === task.id;
            return (
              <div
                key={task.id}
                        className={`flex border-b border-gray-100 dark:border-gray-700/50 transition-colors group ${
                  isSelected
                    ? 'bg-blue-50/90 dark:bg-blue-950/40 border-l-2 border-l-blue-500 dark:border-l-blue-400'
                    : 'hover:bg-gray-50/50 dark:hover:bg-gray-700/20'
                }`}
              >
                {!embedded && (
                  <div className="w-52 shrink-0 sticky left-0 z-10 px-3 py-2 flex items-center gap-2 border-r border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)] dark:shadow-[2px_0_4px_-2px_rgba(0,0,0,0.3)]">
                    <span className="truncate font-medium text-gray-800 dark:text-gray-200">{task.title}</span>
                    {priorityOpt && (
                      <Tag color={priorityOpt.color} className="text-xs m-0 shrink-0">
                        {priorityOpt.label}
                      </Tag>
                    )}
                    <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                      {getColumnTitle(task.columnId)}
                    </span>
                    <Space className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button type="link" size="small" onClick={() => onEdit(task)}>
                        编辑
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        danger
                        onClick={() =>
                          Modal.confirm({
                            title: '删除任务',
                            content: '确定要删除此任务吗？',
                            okText: '删除',
                            okType: 'danger',
                            cancelText: '取消',
                            onOk: () => onDelete(task.id),
                          })
                        }
                      >
                        删除
                      </Button>
                    </Space>
                  </div>
                )}
                <div className="flex-1 relative py-1" style={{ width: timelineWidth, minHeight: 28 }}>
                  <GanttTaskBar
                    task={task}
                    left={left}
                    width={width}
                    start={start}
                    end={end}
                    rangeStart={rangeStart}
                    totalMs={totalMs}
                    timelineWidth={timelineWidth}
                    isSelected={isSelected}
                    onEdit={onEdit}
                    onUpdateDates={onUpdateDates}
                  />
                </div>
              </div>
            );
          })}
          </div>
        </div>
      </div>
  );

  return embedded ? (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">{content}</div>
  ) : (
    <Card className="rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm overflow-hidden">
      {content}
    </Card>
  );
}

export default function Plans() {
  const queryClient = useQueryClient();
  const { currentBotId, addToast } = useAppStore();
  const [board, setBoard] = useState<PlanBoard>(createDefaultBoard);
  const [viewMode, setViewMode] = useState<'kanban' | 'list' | 'plan'>('plan');
  const [ganttGranularity, setGanttGranularity] = useState<GanttGranularity>(loadGanttGranularity);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  /** 从看板某列点击「添加任务」时预填的状态列 */
  const [createDefaultColumnId, setCreateDefaultColumnId] = useState<string | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<PlanTask | null>(null);
  const [form] = Form.useForm();
  /** 甘特图筛选：列、优先级、仅逾期 */
  const [ganttFilterColumns, setGanttFilterColumns] = useState<string[] | null>(null);
  const [ganttFilterPriority, setGanttFilterPriority] = useState<PlanTaskPriority | null>(null);
  const [ganttFilterOverdueOnly, setGanttFilterOverdueOnly] = useState(false);
  const [ganttFullscreenOpen, setGanttFullscreenOpen] = useState(false);
  /** 甘特图视图基准日期，用于「跳转今日」 */
  const [ganttViewDate, setGanttViewDate] = useState<Date | null>(null);

  useEffect(() => {
    if (createModalOpen && createDefaultColumnId) {
      form.setFieldsValue({ columnId: createDefaultColumnId });
      setCreateDefaultColumnId(null);
    }
  }, [createModalOpen, createDefaultColumnId, form]);

  const { data, isLoading, error } = useQuery({
    queryKey: [QUERY_KEY, currentBotId],
    queryFn: () => api.getPlans(currentBotId!),
    enabled: !!currentBotId,
  });

  useEffect(() => {
    if (data) {
      const b = {
        ...data,
        columns: data.columns?.length ? data.columns : DEFAULT_COLUMNS,
        tasks: data.tasks ?? [],
      };
      setBoard(b);
    } else if (currentBotId && !isLoading && error) {
      setBoard(loadFromStorage(currentBotId));
    }
  }, [data, currentBotId, isLoading, error]);

  const saveMutation = useMutation({
    mutationFn: (b: PlanBoard) => api.savePlans(b, currentBotId!),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, currentBotId] });
      setBoard(saved);
    },
    onError: (err: Error, variables: PlanBoard) => {
      addToast({ type: 'error', message: `保存失败: ${err.message}` });
      if (currentBotId) saveToStorage(currentBotId, variables);
    },
  });

  const persistBoard = (newBoard: PlanBoard) => {
    setBoard(newBoard);
    saveMutation.mutate(newBoard);
  };

  type TaskFormValues = {
    title: string;
    description?: string;
    columnId: string;
    priority?: PlanTaskPriority;
    startDate?: string;
    dueDate?: string;
    progress?: number;
    dependencies?: string[];
    type?: PlanTaskType;
    project?: string;
  };

  const handleCreate = (values: TaskFormValues) => {
    const now = new Date().toISOString();
    const startDate = values.startDate ? new Date(values.startDate).toISOString() : undefined;
    const dueDate = values.dueDate ? new Date(values.dueDate).toISOString() : undefined;
    const progress = values.progress != null ? Math.max(0, Math.min(100, values.progress)) : undefined;
    const task: PlanTask = {
      id: generateId(),
      title: values.title.trim(),
      description: values.description?.trim() || undefined,
      columnId: values.columnId,
      order: board.tasks.filter((t) => t.columnId === values.columnId).length,
      createdAt: now,
      updatedAt: now,
      priority: values.priority,
      startDate,
      dueDate,
      progress,
      dependencies: values.dependencies?.length ? values.dependencies : undefined,
      type: values.type,
      project: values.project?.trim() || undefined,
    };
    persistBoard({ ...board, tasks: [...board.tasks, task] });
    setCreateModalOpen(false);
    setCreateDefaultColumnId(null);
    form.resetFields();
  };

  const handleEdit = (task: PlanTask) => {
    setEditingTask(task);
    form.setFieldsValue({
      title: task.title,
      description: task.description || '',
      priority: task.priority,
      startDate: toDateTimeLocal(task.startDate),
      dueDate: toDateTimeLocal(task.dueDate),
      progress: task.progress ?? 0,
      dependencies: task.dependencies ?? [],
      type: task.type ?? 'task',
      project: task.project ?? undefined,
    });
    setEditModalOpen(true);
  };

  const handleUpdate = (values: TaskFormValues) => {
    if (!editingTask) return;
    const now = new Date().toISOString();
    const startDate = values.startDate ? new Date(values.startDate).toISOString() : undefined;
    const dueDate = values.dueDate ? new Date(values.dueDate).toISOString() : undefined;
    const progress = values.progress != null ? Math.max(0, Math.min(100, values.progress)) : undefined;
    const newBoard: PlanBoard = {
      ...board,
      tasks: board.tasks.map((t) =>
        t.id === editingTask.id
          ? {
              ...t,
              title: values.title.trim(),
              description: values.description?.trim() || undefined,
              priority: values.priority,
              startDate,
              dueDate,
              progress,
              dependencies: values.dependencies?.length ? values.dependencies : undefined,
              type: values.type,
              project: values.project?.trim() || undefined,
              updatedAt: now,
            }
          : t
      ),
    };
    persistBoard(newBoard);
    setEditModalOpen(false);
    setEditingTask(null);
    form.resetFields();
  };

  const handleDelete = (taskId: string) => {
    persistBoard({ ...board, tasks: board.tasks.filter((t) => t.id !== taskId) });
  };

  const handleUpdateTaskDates = (taskId: string, startDate: string, dueDate: string) => {
    const now = new Date().toISOString();
    const newBoard: PlanBoard = {
      ...board,
      tasks: board.tasks.map((t) =>
        t.id === taskId ? { ...t, startDate, dueDate, updatedAt: now } : t
      ),
    };
    persistBoard(newBoard);
  };

  const handleProgressChange = (taskId: string, progress: number) => {
    const now = new Date().toISOString();
    const value = Math.max(0, Math.min(100, progress));
    const newBoard: PlanBoard = {
      ...board,
      tasks: board.tasks.map((t) =>
        t.id === taskId ? { ...t, progress: value, updatedAt: now } : t
      ),
    };
    persistBoard(newBoard);
  };

  const handleMove = (taskId: string, columnId: string) => {
    const now = new Date().toISOString();
    const newBoard: PlanBoard = {
      ...board,
      tasks: board.tasks.map((t) =>
        t.id === taskId ? { ...t, columnId, order: 0, updatedAt: now } : t
      ),
    };
    persistBoard(newBoard);
  };

  const getTasksByColumn = (columnId: string) =>
    board.tasks
      .filter((t) => t.columnId === columnId)
      .sort((a, b) => a.order - b.order);

  /** 甘特图视图下根据筛选条件过滤后的任务 */
  const ganttFilteredTasks = useMemo(() => {
    let list = board.tasks;
    if (ganttFilterColumns != null && ganttFilterColumns.length > 0) {
      list = list.filter((t) => ganttFilterColumns.includes(t.columnId));
    }
    if (ganttFilterPriority != null) {
      list = list.filter((t) => t.priority === ganttFilterPriority);
    }
    if (ganttFilterOverdueOnly) {
      list = list.filter((t) => t.dueDate && isOverdue(t.dueDate));
    }
    return list;
  }, [board.tasks, ganttFilterColumns, ganttFilterPriority, ganttFilterOverdueOnly]);

  const sortedTasks = [...board.tasks].sort((a, b) => {
    const colA = board.columns.findIndex((c) => c.id === a.columnId);
    const colB = board.columns.findIndex((c) => c.id === b.columnId);
    if (colA !== colB) return colA - colB;
    const dueA = a.dueDate ? new Date(a.dueDate).getTime() : Infinity;
    const dueB = b.dueDate ? new Date(b.dueDate).getTime() : Infinity;
    return dueA - dueB;
  });

  const renderTaskCard = (task: PlanTask) => {
    const priorityOpt = PRIORITY_OPTIONS.find((p) => p.value === task.priority);
    const overdue = task.dueDate && isOverdue(task.dueDate);
    const priorityBorder =
      task.priority === 'high'
        ? 'border-l-red-500'
        : task.priority === 'medium'
          ? 'border-l-amber-500'
          : task.priority === 'low'
            ? 'border-l-emerald-500'
            : 'border-l-transparent';
    return (
      <Card
        key={task.id}
        size="small"
        className={`rounded-xl border border-gray-100 dark:border-gray-700/80 bg-white dark:bg-gray-800/60 shadow-sm hover:shadow-md hover:border-indigo-200 dark:hover:border-indigo-800/50 transition-all duration-200 border-l-4 ${priorityBorder}`}
        styles={{ body: { padding: '0.75rem 1rem' } }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Typography.Text strong className="block truncate text-gray-800 dark:text-gray-100">
                {task.title}
              </Typography.Text>
              {priorityOpt && (
                <Tag color={priorityOpt.color} className="text-xs m-0 shrink-0">
                  {priorityOpt.label}
                </Tag>
              )}
              {overdue && (
                <Tag color="red" className="text-xs m-0 shrink-0 flex items-center gap-0.5">
                  <ClockCircleOutlined className="text-[10px]" />
                  已逾期
                </Tag>
              )}
            </div>
            {task.description && (
              <Typography.Text
                type="secondary"
                className="text-xs block mt-0.5 line-clamp-2"
              >
                {task.description}
              </Typography.Text>
            )}
            <div className="flex items-center gap-3 mt-1.5 flex-wrap text-xs">
              {task.dueDate && (
                <span className={overdue ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}>
                  {overdue ? '' : '截止 '}
                  {formatDateTime(task.dueDate)}
                </span>
              )}
            </div>
            {typeof task.progress === 'number' && task.progress > 0 && (
              <div className="mt-2">
                <div className="h-1 w-full rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-indigo-500 dark:bg-indigo-400 transition-all"
                    style={{ width: `${Math.min(100, task.progress)}%` }}
                  />
                </div>
                <span className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{task.progress}%</span>
              </div>
            )}
          </div>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'edit',
                  icon: <EditOutlined />,
                  label: '编辑',
                  onClick: () => handleEdit(task),
                },
                ...board.columns
                  .filter((c) => c.id !== task.columnId)
                  .map((c) => ({
                    key: `move-${c.id}`,
                    label: `移动到 ${c.title}`,
                    onClick: () => handleMove(task.id, c.id),
                  })),
                { type: 'divider' as const },
                {
                  key: 'delete',
                  danger: true,
                  label: '删除',
                  onClick: () => {
                    Modal.confirm({
                      title: '删除任务',
                      content: '确定要删除此任务吗？',
                      okText: '删除',
                      okType: 'danger',
                      cancelText: '取消',
                      onOk: () => handleDelete(task.id),
                    });
                  },
                },
              ],
            }}
            trigger={['click']}
          >
            <Button type="text" size="small" icon={<MoreOutlined />} className="shrink-0 opacity-70 hover:opacity-100" />
          </Dropdown>
        </div>
      </Card>
    );
  };

  const listColumns: ColumnsType<PlanTask> = [
    {
      title: '状态',
      dataIndex: 'columnId',
      key: 'columnId',
      width: 100,
      render: (colId) => {
        const style = getColumnStyle(colId);
        return (
          <Space size="small">
            <span className={`w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
            <span>{getColumnTitle(board.columns, colId)}</span>
          </Space>
        );
      },
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (_, task) => (
        <Space>
          <span>{task.title}</span>
          {task.priority && (
            <Space size="small">
              <span className={`w-2 h-2 rounded-full ${PRIORITY_OPTIONS.find((p) => p.value === task.priority)?.dot ?? ''}`} />
              <span>{getPriorityLabel(task.priority)}</span>
            </Space>
          )}
        </Space>
      ),
    },
    {
      title: '截止时间',
      dataIndex: 'dueDate',
      key: 'dueDate',
      width: 180,
      render: (d) =>
        d ? (
          <span className={isOverdue(d) ? 'text-red-500' : ''}>
            {isOverdue(d) ? '已逾期 ' : ''}
            {formatDateTime(d)}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, task) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleEdit(task)}>
            编辑
          </Button>
          <Dropdown
            menu={{
              items: [
                ...board.columns
                  .filter((c) => c.id !== task.columnId)
                  .map((c) => ({
                    key: `move-${c.id}`,
                    label: `移动到 ${c.title}`,
                    onClick: () => handleMove(task.id, c.id),
                  })),
                { type: 'divider' as const },
                {
                  key: 'delete',
                  danger: true,
                  label: '删除',
                  onClick: () =>
                    Modal.confirm({
                      title: '删除任务',
                      content: '确定要删除此任务吗？',
                      okText: '删除',
                      okType: 'danger',
                      cancelText: '取消',
                      onOk: () => handleDelete(task.id),
                    }),
                },
              ],
            }}
          >
            <Button type="link" size="small">
              更多
            </Button>
          </Dropdown>
        </Space>
      ),
    },
  ];

  if (!currentBotId) {
    return (
      <div className="p-6 flex flex-col flex-1 min-h-0">
        <Empty description="请先选择 Bot" className="py-20" />
      </div>
    );
  }

  if (isLoading && !data) {
    return (
      <div className="p-6 flex flex-col flex-1 min-h-0 items-center justify-center">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="p-5 flex flex-col flex-1 min-h-0 bg-gray-50/80 dark:bg-gray-900/50">
      <div className="flex items-center justify-between shrink-0 mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100 tracking-tight">
            项目计划
          </h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            看板、甘特图、列表多视图管理任务，支持优先级与截止时间
          </p>
        </div>
        <div className="flex items-center gap-0 rounded-xl border border-gray-200/90 dark:border-gray-600/80 bg-white dark:bg-gray-800/85 shadow-sm pl-1 pr-1.5 py-1">
          <Segmented
            value={viewMode}
            onChange={(v) => setViewMode(v as 'kanban' | 'list' | 'plan')}
            size="middle"
            className="!bg-transparent plans-toolbar-segmented
              [&_.ant-segmented-item]:min-w-[4.5rem] [&_.ant-segmented-item]:!px-2.5 [&_.ant-segmented-item]:!py-1
              [&_.ant-segmented-item]:text-xs [&_.ant-segmented-item]:text-gray-600 dark:[&_.ant-segmented-item]:text-gray-300
              [&_.ant-segmented-item]:rounded-lg [&_.ant-segmented-item]:border-0 [&_.ant-segmented-item]:shadow-none
              [&_.ant-segmented-item-selected]:!bg-white dark:[&_.ant-segmented-item-selected]:!bg-gray-700
              [&_.ant-segmented-item-selected]:!text-gray-900 dark:[&_.ant-segmented-item-selected]:!text-gray-100
              [&_.ant-segmented-item-selected]:shadow-[0_1px_2px_rgba(0,0,0,0.06)] dark:[&_.ant-segmented-item-selected]:shadow-[0_1px_2px_rgba(0,0,0,0.25)]
              [&_.ant-segmented-item-selected]:font-semibold
              [&_.ant-segmented-thumb]:rounded-lg"
            options={[
              {
                value: 'plan',
                label: (
                  <span className="inline-flex items-center justify-center gap-1.5">
                    <ScheduleOutlined className="text-[14px]" />
                    计划
                  </span>
                ),
              },
              {
                value: 'kanban',
                label: (
                  <span className="inline-flex items-center justify-center gap-1.5">
                    <AppstoreOutlined className="text-[14px]" />
                    看板
                  </span>
                ),
              },
              {
                value: 'list',
                label: (
                  <span className="inline-flex items-center justify-center gap-1.5">
                    <UnorderedListOutlined className="text-[14px]" />
                    列表
                  </span>
                ),
              },
            ]}
          />
          <div
            className="w-px h-6 shrink-0 mx-1.5 bg-gray-200/90 dark:bg-gray-600/90"
            aria-hidden
          />
          <Button
            type="primary"
            size="middle"
            icon={<PlusOutlined />}
            onClick={() => {
              setCreateDefaultColumnId(null);
              setCreateModalOpen(true);
              form.setFieldsValue({ columnId: board.columns[0]?.id });
            }}
            className="!h-8 !px-4 !text-sm !font-medium shadow-sm !bg-emerald-600 hover:!bg-emerald-500 !border-emerald-600"
          >
            创建
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-x-auto flex flex-col">
        {viewMode === 'plan' ? (
          <div className="flex flex-col flex-1 min-h-0 gap-2">
            <div className="flex items-center justify-between shrink-0 px-1">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">时间刻度</span>
                <Select
                  value={ganttGranularity}
                  onChange={(v) => {
                    setGanttGranularity(v);
                    saveGanttGranularity(v);
                  }}
                  options={GANTT_GRANULARITY_OPTIONS}
                  size="small"
                  style={{ width: 100 }}
                  className="text-xs"
                  title="甘特图横轴时间刻度"
                />
              </div>
              <Space size={4}>
                <Dropdown
                  trigger={['click']}
                  popupRender={() => (
                    <Card size="small" className="shadow-lg min-w-[200px]" styles={{ body: { padding: 12 } }}>
                      <div className="space-y-3">
                        <div>
                          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">状态列</div>
                          <Checkbox.Group
                            value={ganttFilterColumns ?? board.columns.map((c) => c.id)}
                            onChange={(vals) => setGanttFilterColumns(vals.length === board.columns.length ? null : (vals as string[]))}
                            className="flex flex-col gap-1"
                          >
                            {board.columns.map((c) => (
                              <Checkbox key={c.id} value={c.id}>
                                <span className="text-xs">{c.title}</span>
                              </Checkbox>
                            ))}
                          </Checkbox.Group>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">优先级</div>
                          <Select
                            value={ganttFilterPriority ?? undefined}
                            placeholder="全部"
                            allowClear
                            size="small"
                            className="w-full"
                            options={[{ value: undefined, label: '全部' }, ...PRIORITY_OPTIONS.map((p) => ({ value: p.value, label: p.label }))]}
                            onChange={(v) => setGanttFilterPriority(v ?? null)}
                          />
                        </div>
                        <Checkbox
                          checked={ganttFilterOverdueOnly}
                          onChange={(e) => setGanttFilterOverdueOnly(e.target.checked)}
                        >
                          <span className="text-xs">仅逾期</span>
                        </Checkbox>
                        <Button type="link" size="small" className="!px-0" onClick={() => { setGanttFilterColumns(null); setGanttFilterPriority(null); setGanttFilterOverdueOnly(false); }}>
                          重置筛选
                        </Button>
                      </div>
                    </Card>
                  )}
                >
                  <Tooltip title="筛选任务">
                    <Button
                      type="text"
                      size="small"
                      icon={<FilterOutlined />}
                      className={`!w-8 !h-8 ${ganttFilterColumns != null || ganttFilterPriority != null || ganttFilterOverdueOnly ? '!text-blue-500' : '!text-gray-400 hover:!text-gray-600'}`}
                    />
                  </Tooltip>
                </Dropdown>
                <Tooltip title="全屏查看甘特图">
                  <Button
                    type="text"
                    size="small"
                    icon={<FullscreenOutlined />}
                    className="!text-gray-400 hover:!text-gray-600 !w-8 !h-8"
                    onClick={() => setGanttFullscreenOpen(true)}
                  />
                </Tooltip>
                <Tooltip title="跳转到今日">
                  <Button
                    type="text"
                    size="small"
                    icon={<CalendarOutlined />}
                    className="!text-gray-400 hover:!text-gray-600 !w-8 !h-8"
                    onClick={() => setGanttViewDate(new Date())}
                  />
                </Tooltip>
              </Space>
            </div>
            <div className="flex-1 min-h-0 rounded-xl border border-gray-200 dark:border-gray-600/80 bg-white dark:bg-gray-800/50 overflow-hidden flex flex-col">
              <ProfessionalGantt
                planTasks={ganttFilteredTasks}
                planColumns={board.columns}
                viewMode={ganttGranularity as GanttViewMode}
                getColumnStyle={(id) => ({ dot: getColumnStyle(id).dot })}
                getColumnTitle={(colId) => getColumnTitle(board.columns, colId)}
                priorityOptions={PRIORITY_OPTIONS}
                onDateChange={handleUpdateTaskDates}
                onProgressChange={handleProgressChange}
                onEdit={handleEdit}
                onDelete={handleDelete}
                listCellWidth="220px"
                viewDateOverride={ganttViewDate ?? undefined}
              />
            </div>
          </div>
        ) : viewMode === 'kanban' ? (
          <div className="flex gap-4 pb-4 flex-1 min-w-0 overflow-x-auto">
            {board.columns.map((col) => {
              const style = getColumnStyle(col.id);
              const count = getTasksByColumn(col.id).length;
              const isEmpty = count === 0;
              const openCreateInColumn = () => {
                setCreateDefaultColumnId(col.id);
                setCreateModalOpen(true);
              };
              return (
                <div
                  key={col.id}
                  className={`flex flex-col w-80 shrink-0 min-w-[280px] max-w-[360px] rounded-2xl border ${style.border} ${style.bg} shadow-sm transition-all duration-200 hover:shadow-md`}
                >
                  <div className="px-4 py-3 border-b border-inherit flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
                      <span className={`font-semibold ${style.accent}`}>{col.title}</span>
                    </div>
                    <span className="text-xs font-medium text-gray-400 dark:text-gray-500 bg-white/60 dark:bg-black/20 px-2 py-0.5 rounded-full tabular-nums">
                      {count}
                    </span>
                  </div>
                  <div className="p-3 min-h-[200px] flex flex-col flex-1 overflow-hidden">
                    <div className="space-y-2 flex-1 overflow-y-auto min-h-0">
                      {getTasksByColumn(col.id).map((task) => renderTaskCard(task))}
                      {isEmpty && (
                        <button
                          type="button"
                          onClick={openCreateInColumn}
                          className="w-full py-8 rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-600 hover:border-indigo-300 dark:hover:border-indigo-600 hover:bg-indigo-50/30 dark:hover:bg-indigo-800/10 transition-colors flex flex-col items-center justify-center gap-2 text-gray-400 dark:text-gray-500 hover:text-indigo-500 dark:hover:text-indigo-400"
                        >
                          <PlusOutlined className="text-xl" />
                          <span className="text-sm">添加任务</span>
                          <span className="text-xs opacity-80">或从上方「创建」添加</span>
                        </button>
                      )}
                    </div>
                    {!isEmpty && (
                      <button
                        type="button"
                        onClick={openCreateInColumn}
                        className="mt-2 py-2 rounded-lg border border-dashed border-gray-200 dark:border-gray-600 hover:border-indigo-300 dark:hover:border-indigo-600 hover:bg-indigo-50/20 dark:hover:bg-indigo-800/10 transition-colors flex items-center justify-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 shrink-0"
                      >
                        <PlusOutlined className="text-sm" />
                        添加任务
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Card className="rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm">
            <Table
              dataSource={sortedTasks}
              columns={listColumns}
              rowKey="id"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              size="small"
            />
          </Card>
        )}
      </div>

      <Modal
        title="甘特图"
        open={ganttFullscreenOpen}
        onCancel={() => setGanttFullscreenOpen(false)}
        footer={
          <Button type="primary" onClick={() => setGanttFullscreenOpen(false)}>
            退出全屏
          </Button>
        }
        width="100%"
        style={{ top: 16 }}
        styles={{
          body: {
            height: 'calc(100vh - 120px)',
            minHeight: 400,
            padding: 0,
            overflow: 'auto',
          },
        }}
        destroyOnHidden
        wrapClassName="plans-gantt-fullscreen-modal"
      >
        <div className="h-full min-h-[400px] w-full rounded border border-gray-200 dark:border-gray-600 overflow-auto">
          <ProfessionalGantt
            planTasks={ganttFilteredTasks}
            planColumns={board.columns}
            viewMode={ganttGranularity as GanttViewMode}
            getColumnStyle={(id) => ({ dot: getColumnStyle(id).dot })}
            getColumnTitle={(colId) => getColumnTitle(board.columns, colId)}
            priorityOptions={PRIORITY_OPTIONS}
            onDateChange={handleUpdateTaskDates}
            onProgressChange={handleProgressChange}
            onEdit={(task) => { setGanttFullscreenOpen(false); handleEdit(task); }}
            onDelete={handleDelete}
            listCellWidth="220px"
            ganttHeight={typeof window !== 'undefined' ? Math.max(400, window.innerHeight - 180) : 500}
            viewDateOverride={ganttViewDate ?? undefined}
          />
        </div>
      </Modal>

      <Modal
        title="新建任务"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          setCreateDefaultColumnId(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText="创建"
        width={400}
        className="compact-modal"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ columnId: board.columns[0]?.id, progress: 0, type: 'task' }}
          className="compact-form"
        >
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]} className="!mb-3">
            <Input placeholder="任务标题" size="small" />
          </Form.Item>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="columnId" label="状态" className="!mb-3">
              <Select options={board.columns.map((c) => ({ value: c.id, label: c.title }))} size="small" />
            </Form.Item>
            <Form.Item name="type" label="类型" className="!mb-3">
              <Select
                size="small"
                options={[
                  { value: 'task', label: '任务' },
                  { value: 'milestone', label: '里程碑' },
                  { value: 'project', label: '项目' },
                ]}
              />
            </Form.Item>
          </div>
          <Form.Item name="priority" label="优先级" className="!mb-3">
            <Select
              allowClear
              placeholder="可选"
              size="small"
              options={PRIORITY_OPTIONS.map((p) => ({ value: p.value, label: p.label }))}
            />
          </Form.Item>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="startDate" label="开始时间" className="!mb-3">
              <Input type="datetime-local" step={1} size="small" />
            </Form.Item>
            <Form.Item name="dueDate" label="截止时间" className="!mb-3">
              <Input type="datetime-local" step={1} size="small" />
            </Form.Item>
          </div>
          <Form.Item name="progress" label="进度" className="!mb-3">
            <Slider min={0} max={100} step={1} size="small" />
          </Form.Item>
          <Form.Item name="description" label="描述" className="!mb-3">
            <TextArea rows={2} placeholder="可选描述" size="small" />
          </Form.Item>
          <Form.Item name="project" label="项目/分组" className="!mb-3">
            <Input placeholder="可选，用于甘特图分组" size="small" />
          </Form.Item>
          <Form.Item name="dependencies" label="依赖" className="!mb-0">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择前置任务"
              size="small"
              options={board.tasks.map((t) => ({ value: t.id, label: t.title }))}
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑任务"
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingTask(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText="保存"
        width={400}
      >
        <Form form={form} layout="vertical" onFinish={handleUpdate} className="compact-form">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]} className="!mb-3">
            <Input placeholder="任务标题" size="small" />
          </Form.Item>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="type" label="类型" className="!mb-3">
              <Select
                size="small"
                options={[
                  { value: 'task', label: '任务' },
                  { value: 'milestone', label: '里程碑' },
                  { value: 'project', label: '项目' },
                ]}
              />
            </Form.Item>
            <Form.Item name="priority" label="优先级" className="!mb-3">
              <Select
                allowClear
                placeholder="可选"
                size="small"
                options={PRIORITY_OPTIONS.map((p) => ({ value: p.value, label: p.label }))}
              />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Form.Item name="startDate" label="开始时间" className="!mb-3">
              <Input type="datetime-local" step={1} size="small" />
            </Form.Item>
            <Form.Item name="dueDate" label="截止时间" className="!mb-3">
              <Input type="datetime-local" step={1} size="small" />
            </Form.Item>
          </div>
          <Form.Item name="progress" label="进度" className="!mb-3">
            <Slider min={0} max={100} step={1} size="small" />
          </Form.Item>
          <Form.Item name="description" label="描述" className="!mb-3">
            <TextArea rows={2} placeholder="可选描述" size="small" />
          </Form.Item>
          <Form.Item name="project" label="项目/分组" className="!mb-3">
            <Input placeholder="可选，用于甘特图分组" size="small" />
          </Form.Item>
          <Form.Item name="dependencies" label="依赖" className="!mb-0">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择前置任务"
              size="small"
              options={board.tasks.filter((t) => t.id !== editingTask?.id).map((t) => ({ value: t.id, label: t.title }))}
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export { GanttView };
