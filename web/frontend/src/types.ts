export interface PipelineNode {
  id: string;
  goal: string;
  model: string | null;
  permissions: Record<string, string>;
  depends_on: string[];
  max_iterations: number;
  system_prompt: string | null;
}

export interface PipelineEdge {
  from: string;
  to: string;
  condition?: string;
}

export interface PipelineData {
  name: string;
  strategy: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  levels: string[][];
}

export interface TaskStatus {
  name: string;
  status: string;
  model: string | null;
  iteration: number;
  tool_calls: number;
  started_at: number | null;
  completed_at: number | null;
  duration_ms: number | null;
  error: string | null;
}

export interface RunData {
  run_id: string;
  pipeline_name: string;
  status: string;
  tasks: Record<string, TaskStatus>;
  started_at: number | null;
  completed_at: number | null;
}

export interface AgentInfo {
  name: string;
  pipeline: string;
}

export interface LogEntry {
  type: string;
  text?: string;
  name?: string;
  args?: string;
  iteration?: number;
  phase?: string;
}

export interface LogResponse {
  logs: LogEntry[];
  cursor: number;
  status: string;
}
