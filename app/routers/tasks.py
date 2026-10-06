import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Task, TaskPriority, TaskStatus, User
from app.schemas import TaskCreate, TaskOut, TaskPage, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


def _get_owned_task(db: Session, task_id: int, user: User) -> Task:
    """Tasks owned by other users are reported as 404 so IDs can't be probed."""
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Task {task_id} not found")
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = Task(**data.model_dump(), user_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=TaskPage)
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: TaskStatus | None = Query(None, alias="status"),
    priority: TaskPriority | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conditions = [Task.user_id == user.id]
    if status_filter:
        conditions.append(Task.status == status_filter)
    if priority:
        conditions.append(Task.priority == priority)

    total = db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
    items = db.scalars(
        select(Task)
        .where(*conditions)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TaskPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_owned_task(db, task_id, user)


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = _get_owned_task(db, task_id, user)
    task.title = data.title
    sent = data.model_fields_set
    if "description" in sent:
        task.description = data.description
    if "status" in sent:
        if data.status is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "status cannot be null")
        task.status = data.status
    if "priority" in sent:
        if data.priority is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "priority cannot be null")
        task.priority = data.priority
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = _get_owned_task(db, task_id, user)
    db.delete(task)
    db.commit()
    return {"message": f"Task {task_id} deleted"}
