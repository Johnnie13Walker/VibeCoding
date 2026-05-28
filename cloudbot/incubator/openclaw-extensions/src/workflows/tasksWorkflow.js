import { getTodoConfig, pingTodo } from '../../provider.todo.js';

const tasksWorkflow = {
  async run(_input, context = {}) {
    const todoConfig = getTodoConfig(context);
    const todoPing = await pingTodo(context);

    const lines = [
      'Задачи:',
      `TODO подключение: ${todoConfig.configured ? 'настроено' : 'не настроено'}`,
    ];

    if (todoPing.configured) {
      lines.push(`TODO ping: ${todoPing.ok ? 'OK' : `ошибка (${todoPing.message})`}`);
    } else {
      lines.push('TODO ping: не настроен');
    }

    lines.push('Подсказка: для списка задач подключи TODOIST_API_TOKEN или TODO_API_TOKEN.');

    return {
      response: { text: lines.join('\n') },
      nextState: null,
    };
  },

  async continue(_state, input, context = {}) {
    return this.run(input, context);
  },
};

async function runTasksWorkflow(input, context = {}) {
  const out = await tasksWorkflow.run(input, context);
  return { handled: true, reply: out.response.text };
}

export { tasksWorkflow, runTasksWorkflow };
