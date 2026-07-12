export type Todo = {
    id: string;
    description: string;
    source: string;
    status: TodoStatus;
    doneDate?: Date | string;
    created: Date | string;
};


export enum TodoStatus  {
    Pending = "todo",
    Completed = "done",
    InProgress = "in-progress",
    Cancelled = "cancelled",
};

