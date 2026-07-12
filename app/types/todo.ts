export type Todo = {
    id: string;
    description: string;
    source: string;
    status: TodoStatus;
    doneDate?: Date | string;
    created: Date | string;
};


export enum TodoStatus  {
    Pending = "pending",
    Completed = "done",
    InProgress = "in-progress",
    Cancelled = "cancelled",
};

