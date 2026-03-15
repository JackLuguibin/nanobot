import React, { useCallback, useRef, useState, useEffect } from 'react';
import { Gantt, ViewMode, type Task } from 'gantt-task-react';
import 'gantt-task-react/dist/index.css';
import './ProfessionalGantt.css';
import type { PlanTask, PlanColumn, PlanTaskPriority } from '../api/types_plans';

/** 按列区分的任务条颜色（与看板列风格一致） */
const COLUMN_BAR_STYLES: Record<
  string,
  { backgroundColor: string; backgroundSelectedColor: string; progressColor: string; progressSelectedColor: string }
> = {
  'col-backlog': {
    backgroundColor: '#64748b',
    backgroundSelectedColor: '#475569',
    progressColor: '#94a3b8',
    progressSelectedColor: '#64748b',
  },
  'col-progress': {
    backgroundColor: '#3b82f6',
    backgroundSelectedColor: '#2563eb',
    progressColor: '#60a5fa',
    progressSelectedColor: '#3b82f6',
  },
  'col-done': {
    backgroundColor: '#10b981',
    backgroundSelectedColor: '#059669',
    progressColor: '#34d399',
    progressSelectedColor: '#10b981',
  },
};
const DEFAULT_BAR_STYLE = {
  backgroundColor: '#64748b',
  backgroundSelectedColor: '#475569',
  progressColor: '#94a3b8',
  progressSelectedColor: '#64748b',
};

export type GanttViewMode = 'minute' | 'hour' | 'day' | 'week' | 'month';

const VIEW_MODE_MAP: Record<GanttViewMode, ViewMode> = {
  minute: ViewMode.Hour,
  hour: ViewMode.Hour,
  day: ViewMode.Day,
  week: ViewMode.Week,
  month: ViewMode.Month,
};

/** 各视图下时间列宽（px），保证中文「周X」「月/日」等不重叠 */
const COLUMN_WIDTH: Record<GanttViewMode, number> = {
  minute: 48,
  hour: 52,
  day: 56,
  week: 88,
  month: 112,
};

const HEADER_HEIGHT = 40;
/** 未测量到容器时的默认图表高度 */
const DEFAULT_GANTT_HEIGHT = 400;

const PRE_STEPS_COUNT = 1;

/** 与 gantt-task-react 内部 ganttDateRange 对齐：计算甘特图时间范围与初始 viewDate */
function getGanttDateRange(tasks: Task[], mode: GanttViewMode): [Date, Date] {
  if (tasks.length === 0) {
    const now = new Date();
    return [now, new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000)];
  }
  let minStart = tasks[0].start.getTime();
  let maxEnd = tasks[0].end.getTime();
  tasks.forEach((t) => {
    if (t.start.getTime() < minStart) minStart = t.start.getTime();
    if (t.end.getTime() > maxEnd) maxEnd = t.end.getTime();
  });
  const startOfDay = (d: Date) => {
    const r = new Date(d);
    r.setHours(0, 0, 0, 0);
    return r;
  };
  const startOfMonth = (d: Date) => {
    const r = new Date(d);
    r.setDate(1);
    r.setHours(0, 0, 0, 0);
    return r;
  };
  const getMonday = (d: Date) => {
    const r = new Date(d);
    const day = r.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    r.setDate(r.getDate() + diff);
    r.setHours(0, 0, 0, 0);
    return r;
  };
  const addDays = (d: Date, n: number) => new Date(d.getTime() + n * 24 * 60 * 60 * 1000);
  const addMonths = (d: Date, n: number) => {
    const r = new Date(d);
    r.setMonth(r.getMonth() + n);
    return r;
  };
  const addHours = (d: Date, n: number) => new Date(d.getTime() + n * 60 * 60 * 1000);

  const minStartDate = new Date(minStart);
  const maxEndDate = new Date(maxEnd);

  if (mode === 'month') {
    const newStart = addMonths(startOfMonth(minStartDate), -PRE_STEPS_COUNT);
    const newEnd = startOfMonth(addMonths(maxEndDate, 12));
    return [newStart, newEnd];
  }
  if (mode === 'week') {
    const newStart = addDays(getMonday(startOfDay(minStartDate)), -7 * PRE_STEPS_COUNT);
    const newEnd = addDays(startOfDay(maxEndDate), 7 * 6); // ~1.5 month in days
    return [newStart, newEnd];
  }
  if (mode === 'day') {
    const dayStart = startOfDay(minStartDate);
    const newStart = addDays(dayStart, -PRE_STEPS_COUNT);
    const newEnd = addDays(dayStart, 19);
    return [newStart, newEnd];
  }
  if (mode === 'hour' || mode === 'minute') {
    const hourStart = new Date(minStartDate);
    hourStart.setMinutes(0, 0, 0);
    const newStart = addHours(hourStart, -PRE_STEPS_COUNT);
    const newEnd = addDays(startOfDay(maxEndDate), 1);
    return [newStart, newEnd];
  }
  const now = new Date();
  return [now, new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000)];
}

function planTaskToGanttTask(plan: PlanTask, barStyles: typeof DEFAULT_BAR_STYLE): Task {
  const start = plan.startDate ? new Date(plan.startDate) : new Date(plan.createdAt);
  let end: Date;
  if (plan.type === 'milestone') {
    end = new Date(start.getTime());
  } else if (plan.dueDate) {
    end = new Date(plan.dueDate);
  } else {
    end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
  }
  const progress = Math.max(0, Math.min(100, Number(plan.progress) || 0));
  return {
    id: plan.id,
    name: plan.title,
    type: (plan.type === 'milestone' ? 'milestone' : plan.type === 'project' ? 'project' : 'task') as Task['type'],
    start,
    end,
    progress,
    dependencies: plan.dependencies ?? [],
    styles: barStyles,
    isDisabled: plan.isDisabled,
    project: plan.project,
  };
}

/** 列表用短日期，避免列过宽：MM/DD */
function formatDateShort(d?: string): string {
  if (!d) return '–';
  const date = new Date(d);
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${m}/${day}`;
}

function isOverdue(dueDate?: string): boolean {
  if (!dueDate) return false;
  return new Date(dueDate) < new Date();
}

export interface ColumnStyle {
  dot: string;
}

export interface PriorityOption {
  value: PlanTaskPriority;
  label: string;
  dot: string;
}

interface ProfessionalGanttProps {
  planTasks: PlanTask[];
  planColumns: PlanColumn[];
  viewMode: GanttViewMode;
  getColumnStyle: (columnId: string) => ColumnStyle;
  getColumnTitle: (columnId: string) => string;
  priorityOptions: PriorityOption[];
  onDateChange: (taskId: string, startDate: string, dueDate: string) => void;
  onProgressChange?: (taskId: string, progress: number) => void;
  onEdit: (task: PlanTask) => void;
  onDelete?: (taskId: string) => void;
  /** 左侧任务列表宽度，传空字符串可隐藏列表 */
  listCellWidth?: string;
  /** 甘特图区域高度，不传则随内容撑开 */
  ganttHeight?: number;
  /** 指定视图基准日期（如「跳转今日」），不传则按任务范围自动计算 */
  viewDateOverride?: Date;
}

export function ProfessionalGantt({
  planTasks,
  planColumns,
  viewMode,
  getColumnStyle,
  getColumnTitle,
  priorityOptions,
  onDateChange,
  onProgressChange,
  onEdit,
  onDelete,
  listCellWidth = '260px',
  ganttHeight: ganttHeightProp,
  viewDateOverride,
}: ProfessionalGanttProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [measuredChartHeight, setMeasuredChartHeight] = useState(DEFAULT_GANTT_HEIGHT);

  useEffect(() => {
    if (ganttHeightProp != null && ganttHeightProp > 0) return;
    const el = wrapperRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { height } = entries[0]?.contentRect ?? { height: 0 };
      const chartHeight = Math.max(200, Math.floor(height) - HEADER_HEIGHT);
      setMeasuredChartHeight(chartHeight);
    });
    ro.observe(el);
    const h = el.clientHeight;
    setMeasuredChartHeight(Math.max(200, h - HEADER_HEIGHT));
    return () => ro.disconnect();
  }, [ganttHeightProp]);

  const planById = React.useMemo(() => {
    const m = new Map<string, PlanTask>();
    planTasks.forEach((p) => m.set(p.id, p));
    return m;
  }, [planTasks]);

  const ganttTasks: Task[] = React.useMemo(
    () =>
      [...planTasks]
        .sort((a, b) => {
          const colA = planColumns.findIndex((c) => c.id === a.columnId);
          const colB = planColumns.findIndex((c) => c.id === b.columnId);
          if (colA !== colB) return colA - colB;
          const dueA = a.dueDate ? new Date(a.dueDate).getTime() : Infinity;
          const dueB = b.dueDate ? new Date(b.dueDate).getTime() : Infinity;
          return dueA - dueB;
        })
        .map((plan) => planTaskToGanttTask(plan, COLUMN_BAR_STYLES[plan.columnId] ?? DEFAULT_BAR_STYLE)),
    [planTasks, planColumns]
  );

  const viewDate = React.useMemo(() => {
    if (viewDateOverride) return viewDateOverride;
    const [start] = getGanttDateRange(ganttTasks, viewMode);
    return start;
  }, [ganttTasks, viewMode, viewDateOverride]);

  const ganttHeight = ganttHeightProp != null && ganttHeightProp > 0 ? ganttHeightProp : measuredChartHeight;

  const handleDateChange = React.useCallback(
    (task: Task) => {
      onDateChange(task.id, task.start.toISOString(), task.end.toISOString());
    },
    [onDateChange]
  );

  const handleProgressChange = React.useCallback(
    (task: Task) => {
      if (onProgressChange) onProgressChange(task.id, task.progress);
    },
    [onProgressChange]
  );

  const handleDoubleClick = React.useCallback(
    (task: Task) => {
      const plan = planById.get(task.id);
      if (plan) onEdit(plan);
    },
    [planById, onEdit]
  );

  const handleDelete = React.useCallback(
    (task: Task) => {
      if (onDelete) onDelete(task.id);
      return true;
    },
    [onDelete]
  );

  const isNarrowList = listCellWidth ? parseInt(listCellWidth, 10) < 180 : false;

  const TaskListTableCustom = React.useCallback(
    (props: {
      rowHeight: number;
      rowWidth: string;
      fontFamily: string;
      fontSize: string;
      locale: string;
      tasks: Task[];
      selectedTaskId: string;
      setSelectedTask: (taskId: string) => void;
      onExpanderClick: (task: Task) => void;
    }) => {
      const { tasks, selectedTaskId: selId, setSelectedTask, rowHeight } = props;
      const pad = isNarrowList ? 'px-2' : 'px-2';
      const gap = isNarrowList ? 'gap-2' : 'gap-1.5';
      return (
        <div className="gantt-task-list-table overflow-hidden" style={{ fontFamily: props.fontFamily, fontSize: props.fontSize }}>
          {tasks.map((task) => {
            const plan = planById.get(task.id);
            const colStyle = plan ? getColumnStyle(plan.columnId) : { dot: 'bg-gray-400' };
            const isSelected = selId === task.id;
            const startStr = plan ? formatDateShort(plan.startDate ?? plan.createdAt) : '–';
            const endStr = plan ? formatDateShort(plan.dueDate) : '–';
            const fullStart = plan?.startDate ?? plan?.createdAt;
            const fullEnd = plan?.dueDate;
            const title = plan ? `${task.name}\n开始 ${fullStart ? new Date(fullStart).toLocaleDateString('zh-CN') : '–'}  截止 ${fullEnd ? new Date(fullEnd).toLocaleDateString('zh-CN') : '–'}` : task.name;
            return (
              <div
                key={task.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedTask(isSelected ? '' : task.id)}
                onDoubleClick={() => handleDoubleClick(task)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedTask(isSelected ? '' : task.id);
                  }
                }}
                className={`flex items-center ${gap} ${pad} border-b border-[#e2e8f0] dark:border-gray-700/50 cursor-pointer transition-colors bg-white dark:bg-gray-800/50 even:bg-[#f8fafc] dark:even:bg-gray-800/40 hover:bg-[#f1f5f9] dark:hover:bg-gray-700/40 ${isSelected ? 'bg-blue-50/80 dark:bg-blue-950/40 border-l-2 border-l-blue-500 dark:border-l-blue-400' : ''}`}
                style={{ height: rowHeight, minHeight: rowHeight }}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${plan ? colStyle.dot : 'bg-gray-400'}`} aria-hidden />
                <span className="flex-1 min-w-0 truncate text-gray-800 dark:text-gray-100 font-medium text-xs" title={title}>
                  {task.name}
                </span>
                {!isNarrowList && (
                  <>
                    <span
                      className="text-[10px] shrink-0 w-9 text-right tabular-nums whitespace-nowrap text-gray-600 dark:text-gray-400"
                      title={fullStart ? new Date(fullStart).toLocaleDateString('zh-CN') : undefined}
                    >
                      {startStr}
                    </span>
                    <span
                      className={`text-[10px] shrink-0 w-9 text-right tabular-nums whitespace-nowrap ${
                        plan?.dueDate && isOverdue(plan.dueDate) ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-gray-400'
                      }`}
                      title={fullEnd ? new Date(fullEnd).toLocaleDateString('zh-CN') : undefined}
                    >
                      {endStr}
                    </span>
                  </>
                )}
                <span className="shrink-0 w-9 flex items-center justify-end gap-0.5" title={`进度 ${task.progress}%`}>
                  <span className="w-4 h-1 rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
                    <span
                      className="block h-full rounded-full bg-blue-500 dark:bg-blue-400 transition-all"
                      style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }}
                    />
                  </span>
                  <span className="text-[10px] tabular-nums text-gray-500 dark:text-gray-400 w-4 text-right">{task.progress}%</span>
                </span>
              </div>
            );
          })}
        </div>
      );
    },
    [planById, getColumnStyle, handleDoubleClick, isNarrowList]
  );

  const TaskListHeaderCustom = React.useCallback(
    (props: { headerHeight: number; rowWidth: string; fontFamily: string; fontSize: string }) => (
      <div
        className="gantt-list-header flex items-center gap-1.5 px-2 border-b-2 border-[#e2e8f0] dark:border-gray-600 bg-[#f1f5f9] dark:bg-gray-800/95 text-[10px] font-semibold text-gray-600 dark:text-gray-400"
        style={{ height: props.headerHeight, fontFamily: props.fontFamily, fontSize: props.fontSize }}
      >
        <span className="w-2 shrink-0" aria-hidden />
        <span className="flex-1 min-w-0 truncate">任务</span>
        {!isNarrowList && (
          <>
            <span className="shrink-0 w-9 text-right tabular-nums">开始</span>
            <span className="shrink-0 w-9 text-right tabular-nums">截止</span>
          </>
        )}
        <span className="shrink-0 w-9 text-right tabular-nums">进度</span>
      </div>
    ),
    [isNarrowList]
  );

  if (ganttTasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
        <p className="text-sm">暂无任务</p>
        <p className="text-xs mt-1">创建任务后可在此查看甘特图</p>
      </div>
    );
  }

  return (
    <div
      ref={wrapperRef}
      className="professional-gantt-wrapper gantt-limited-height flex flex-col flex-1 min-h-0 overflow-hidden [&_.gantt-task-list-table]:!border-0 [&_table]:text-xs [&_table_td]:whitespace-nowrap"
      style={{ ['--gantt-list-width' as string]: listCellWidth }}
    >
      <Gantt
        tasks={ganttTasks}
        viewMode={VIEW_MODE_MAP[viewMode]}
        viewDate={viewDate}
        locale="zh-CN"
        listCellWidth={listCellWidth}
        columnWidth={COLUMN_WIDTH[viewMode]}
        rowHeight={40}
        headerHeight={HEADER_HEIGHT}
        ganttHeight={ganttHeight}
        barFill={85}
        barCornerRadius={4}
        barBackgroundColor="#64748b"
        barBackgroundSelectedColor="#3b82f6"
        barProgressColor="#94a3b8"
        barProgressSelectedColor="#60a5fa"
        todayColor="rgba(251, 191, 36, 0.18)"
        fontFamily="inherit"
        fontSize="12px"
        TaskListTable={listCellWidth ? TaskListTableCustom : undefined}
        TaskListHeader={listCellWidth ? TaskListHeaderCustom : undefined}
        onDateChange={handleDateChange}
        onProgressChange={onProgressChange ? handleProgressChange : undefined}
        onDoubleClick={handleDoubleClick}
        onDelete={onDelete ? handleDelete : undefined}
      />
    </div>
  );
}
