import React from 'react';
import TaskCard from './TaskCard';
import CreateSprintModal from './modals/CreateSprintModal';
import CreateTaskModal from './modals/CreateTaskModal';
import TaskDetailsModal from './modals/TaskDetailsModal';
import TaskHistoryModal from './modals/TaskHistoryModal';

export default function ProjectBoardView({
  selectedProject,
  onBack,
  boardError,
  boardLoading,
  onOpenTaskModal,
  onOpenSprintModal,
  backlogTasks,
  taskUnreadCount,
  onDeleteTask,
  onOpenTaskDetails,
  TaskProgressComponent,
  sprints,
  sprintTasksSorted,
  expandedSprints,
  toggleSprint,
  moveTaskToSprint,
  setTaskForm,
  showTaskModal,
  setShowTaskModal,
  createTask,
  taskForm,
  setTaskFormState,
  statusOptions,
  showSprintModal,
  setShowSprintModal,
  createSprint,
  sprintForm,
  setSprintForm,
  onDeleteSprint,
  toSprintDateLabel,
  taskDetails,
  closeTaskDetails,
  setShowTaskHistoryModal,
  saveTaskDetails,
  taskDetailsEditing,
  setTaskDetailsEditing,
  setTaskDetails,
  isTaskDetailsEditing,
  commentsLoading,
  comments,
  commentText,
  setCommentText,
  createComment,
  toDeadlineLabel,
  showTaskHistoryModal,
  taskHistoryLoading,
  taskHistory,
  historyEventLabel,
  historyFieldLabel,
  historyValueLabel,
}) {
  return (
    <main className="app">
      <div className="screen-header">
        <h1 className="screen-title">{selectedProject.title}</h1>
        <p className="screen-subtitle">Задачи и спринты проекта</p>
      </div>

      <button className="back-btn" onClick={onBack}>
        Назад к списку проектов
      </button>

      {boardError && <p className="auth-hint">{boardError}</p>}

      <div className="board-actions">
        <button className="open-btn" onClick={onOpenTaskModal}>
          Новая задача
        </button>
        <button className="open-btn" onClick={onOpenSprintModal}>
          Новый спринт
        </button>
      </div>

      {boardLoading && <div className="empty">Загружаем данные проекта...</div>}

      {!boardLoading && (
        <div className="board-grid">
          <section className="card">
            <h3>Задачи</h3>
            <p className="screen-subtitle">Перетащите задачу в спринт, чтобы добавить ее в план.</p>
            <div className="task-list">
              {backlogTasks.length === 0 && <div className="empty compact">Свободных задач нет</div>}
              {backlogTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  unreadCount={taskUnreadCount(task)}
                  onDelete={(item) => void onDeleteTask(item.id, item.title)}
                  onOpen={onOpenTaskDetails}
                  TaskProgressComponent={TaskProgressComponent}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/task-id', String(task.id))}
                />
              ))}
            </div>
          </section>

          <section className="card">
            <h3>Спринты</h3>
            <div className="sprint-list">
              {sprints.length === 0 && <div className="empty compact">Спринтов пока нет</div>}
              {sprints.map((sprint) => {
                const sprintTasks = sprintTasksSorted(sprint.id);
                const doneCount = sprintTasks.filter((task) => task.status === 'DONE').length;
                const sprintProgress = sprintTasks.length ? Math.round((doneCount / sprintTasks.length) * 100) : 0;
                const isOpen = !!expandedSprints[sprint.id];

                return (
                  <article
                    key={sprint.id}
                    className="sprint-card"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      const draggedTaskId = Number(e.dataTransfer.getData('text/task-id'));
                      if (draggedTaskId) void moveTaskToSprint(draggedTaskId, sprint.id);
                    }}
                  >
                    <button
                      type="button"
                      className="sprint-delete-btn"
                      onClick={(event) => {
                        event.stopPropagation();
                        void onDeleteSprint(sprint.id, sprint.title);
                      }}
                      aria-label="Удалить спринт"
                      title="Удалить спринт"
                    >
                      🗑
                    </button>
                    <button type="button" className="sprint-header" onClick={() => toggleSprint(sprint.id, isOpen)}>
                      <strong>{sprint.title}</strong>
                      <span>{isOpen ? 'Свернуть' : 'Открыть'}</span>
                    </button>
                    <p className="screen-subtitle sprint-dates">
                      Срок спринта: {toSprintDateLabel(sprint.start_date)} - {toSprintDateLabel(sprint.end_date)}
                    </p>
                    <div className="progress-line sprint-progress">
                      <div className="progress-fill" style={{ width: `${sprintProgress}%` }} />
                    </div>
                    <p className="screen-subtitle">
                      Выполнено: {doneCount} из {sprintTasks.length}
                    </p>
                    {isOpen && (
                      <>
                        <button
                          className="open-btn small-btn"
                          type="button"
                          onClick={() => {
                            setShowTaskModal(true);
                            setTaskForm((prev) => ({ ...prev, sprint_id: String(sprint.id) }));
                          }}
                        >
                          Добавить задачу в спринт
                        </button>
                        <div className="task-list">
                          {sprintTasks.length === 0 && <div className="empty compact">Задач в спринте нет</div>}
                          {sprintTasks.map((task) => (
                            <TaskCard
                              key={task.id}
                              task={task}
                              unreadCount={taskUnreadCount(task)}
                              onDelete={(item) => void onDeleteTask(item.id, item.title)}
                              onOpen={onOpenTaskDetails}
                              TaskProgressComponent={TaskProgressComponent}
                            />
                          ))}
                        </div>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      )}

      <CreateTaskModal
        show={showTaskModal}
        onClose={() => setShowTaskModal(false)}
        onSubmit={createTask}
        taskForm={taskForm}
        setTaskForm={setTaskFormState}
        sprints={sprints}
        statusOptions={statusOptions}
      />

      <CreateSprintModal
        show={showSprintModal}
        onClose={() => setShowSprintModal(false)}
        onSubmit={createSprint}
        sprintForm={sprintForm}
        setSprintForm={setSprintForm}
      />

      <TaskDetailsModal
        taskDetails={taskDetails}
        onClose={closeTaskDetails}
        onOpenHistory={() => setShowTaskHistoryModal(true)}
        onSubmit={saveTaskDetails}
        taskDetailsEditing={taskDetailsEditing}
        setTaskDetailsEditing={setTaskDetailsEditing}
        setTaskDetails={setTaskDetails}
        statusOptions={statusOptions}
        isTaskDetailsEditing={isTaskDetailsEditing}
        commentsLoading={commentsLoading}
        comments={comments}
        commentText={commentText}
        setCommentText={setCommentText}
        onCreateComment={createComment}
        toDeadlineLabel={toDeadlineLabel}
      />

      <TaskHistoryModal
        show={!!taskDetails && showTaskHistoryModal}
        onClose={() => setShowTaskHistoryModal(false)}
        taskVersion={taskDetails?.version}
        taskHistoryLoading={taskHistoryLoading}
        taskHistory={taskHistory}
        historyEventLabel={historyEventLabel}
        historyFieldLabel={historyFieldLabel}
        historyValueLabel={historyValueLabel}
        toDeadlineLabel={toDeadlineLabel}
      />
    </main>
  );
}
