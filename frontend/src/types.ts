export type Role = "student" | "teacher";
export type User = { id: number; role: Role; name: string; login_code: string };

export type SlotSpec = "text" | string[];
export type Template = { tag: string; judgement: "wrong" | "right"; body: string; slots: Record<string, SlotSpec> };
export type Templates = { kind: string; tags: string[]; templates: Template[] };

export type Status = "not_started" | "in_progress" | "done" | "late_done" | "overdue";

export type AssignmentSummary = {
  id: number;
  title: string;
  assigned_at: string;
  due_at: string;
  submitted_at: string | null;
  is_late: boolean;
  status: Status;
  total: number;
  answered: number;
};

export type StudentItem = { id: number; passage_id: string; no: number; choice: string; sentence: string };
export type AnswerValue = { judgement: boolean; tag: string; slots: Record<string, string> };

export type StudentAssignment = AssignmentSummary & {
  kind: string;
  item_order: number[];
  passages: { id: string; source: string; text: string }[];
  items: StudentItem[];
  answers: Record<string, AnswerValue & { saved_at: string }>;
};

export type Correct = { is_correct: boolean; tag: string; model_slots: Record<string, string>; explanation: string };

export type ResultItem = {
  id: number;
  no: number;
  choice: string;
  sentence: string;
  mine: AnswerValue;
  correct: Correct;
  judgement_ok: boolean;
  tag_ok: boolean;
};

export type StudentResult = AssignmentSummary & {
  kind: string;
  passages: { id: string; source: string; text: string; items: ResultItem[] }[];
};
