/** Plans 看板相关类型 */

export interface PlanColumn {
  id: string;
  title: string;
  order: number;
}

export type PlanTaskPriority = 'high' | 'medium' | 'low';

/** 甘特图任务类型：task 普通任务，milestone 里程碑，project 项目（可折叠子任务） */
export type PlanTaskType = 'task' | 'milestone' | 'project';

export interface PlanTask {
  id: string;
  title: string;
  description?: string;
  columnId: string;
  order: number;
  createdAt: string;
  updatedAt: string;
  /** 优先级：高/中/低 */
  priority?: PlanTaskPriority;
  /** 开始日期 ISO 字符串（甘特图用，缺省时用 createdAt） */
  startDate?: string;
  /** 截止日期 ISO 字符串 */
  dueDate?: string;
  /** 进度 0–100，甘特图显示进度条 */
  progress?: number;
  /** 依赖的任务 id 列表（这些任务完成后本任务才能开始） */
  dependencies?: string[];
  /** 所属项目/分组名，用于甘特图分组 */
  project?: string;
  /** 任务类型：task | milestone | project，默认 task */
  type?: PlanTaskType;
  /** 是否禁用（甘特图不可拖拽等） */
  isDisabled?: boolean;
}

export interface PlanBoard {
  id: string;
  name?: string;
  columns: PlanColumn[];
  tasks: PlanTask[];
}
