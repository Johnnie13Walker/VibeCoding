import { getTodoConfig, pingTodo } from '../../../provider.todo.js';

export async function runTasksWorkflow(_input, ctx = {}) {
  const todoConfig = getTodoConfig(ctx);
  const todoPing = await pingTodo(ctx);

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

  return { handled: true, reply: lines.join('\n') };
}
