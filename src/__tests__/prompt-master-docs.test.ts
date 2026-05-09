import fs from 'fs';
import path from 'path';

const rootDir = path.resolve(__dirname, '../..');
const promptMasterDir = path.join(rootDir, 'agents', 'prompt-master');

const requiredFiles = [
  'system-prompt.md',
  'workflows.md',
  'routing-rules.md',
  'prompt-templates.md',
  'orchestration.md',
  'memory-rules.md',
  'quality-checklist.md',
  'examples/chaotic-to-production.md',
  'examples/multi-agent-orchestration.md',
  'examples/good-bad-prompts.md',
  'schemas/task-intake.schema.json',
  'schemas/agent-routing.schema.json',
];

describe('prompt-master documentation', () => {
  it('contains the required architecture files', () => {
    for (const file of requiredFiles) {
      const filePath = path.join(promptMasterDir, file);
      expect(fs.existsSync(filePath)).toBe(true);
    }
  });

  it('defines prompt-master as a meta-agent that does not execute tasks directly', () => {
    const systemPrompt = fs.readFileSync(path.join(promptMasterDir, 'system-prompt.md'), 'utf8');

    expect(systemPrompt).toContain('meta-agent');
    expect(systemPrompt).toContain('orchestration-agent');
    expect(systemPrompt).toContain('Ты не выполняешь предметную задачу сам');
  });

  it('keeps the mandatory visual orchestration rule', () => {
    const systemPrompt = fs.readFileSync(path.join(promptMasterDir, 'system-prompt.md'), 'utf8');
    const routingRules = fs.readFileSync(path.join(promptMasterDir, 'routing-rules.md'), 'utf8');

    expect(systemPrompt).toContain('Продуктолог');
    expect(systemPrompt).toContain('Дизайнер');
    expect(systemPrompt).toContain('Испытатель');
    expect(routingRules).toContain('Исключений нет');
  });

  it('has valid JSON schemas', () => {
    for (const file of ['task-intake.schema.json', 'agent-routing.schema.json']) {
      const schemaPath = path.join(promptMasterDir, 'schemas', file);
      expect(() => JSON.parse(fs.readFileSync(schemaPath, 'utf8'))).not.toThrow();
    }
  });

  it('routing-rules.md covers every task type from the task-intake schema enum', () => {
    const intakeSchema = JSON.parse(
      fs.readFileSync(path.join(promptMasterDir, 'schemas', 'task-intake.schema.json'), 'utf8')
    );
    const routingRules = fs.readFileSync(path.join(promptMasterDir, 'routing-rules.md'), 'utf8');

    const taskTypes: string[] = intakeSchema.properties.task_types.items.enum;
    expect(taskTypes.length).toBeGreaterThan(0);

    const exemptFromMatrix = new Set(['документация', 'операционный процесс']);

    for (const type of taskTypes) {
      if (exemptFromMatrix.has(type)) {
        continue;
      }
      expect(routingRules).toContain(type);
    }
  });

  it('AGENTS.md declares Master as the only write-worker and others as read-only', () => {
    const agentsDoc = fs.readFileSync(path.join(rootDir, 'AGENTS.md'), 'utf8');

    expect(agentsDoc).toContain('Единственный write-worker');
    expect(agentsDoc).toMatch(/кроме\s+`?Мастера`?,\s+работают\s+в\s+режиме\s+read-only/);
    expect(agentsDoc).toContain('Meta-agent');
  });

  it('shared/MEMORY.md exists and references prompt-master', () => {
    const sharedMemoryPath = path.join(rootDir, 'shared', 'MEMORY.md');
    expect(fs.existsSync(sharedMemoryPath)).toBe(true);

    const sharedMemory = fs.readFileSync(sharedMemoryPath, 'utf8');
    expect(sharedMemory).toContain('prompt-master');
    expect(sharedMemory.length).toBeGreaterThan(200);
  });

  it('orchestration.md describes the escalation procedure on audit failure', () => {
    const orchestration = fs.readFileSync(path.join(promptMasterDir, 'orchestration.md'), 'utf8');

    expect(orchestration).toMatch(/[Ээ]скалац/);
    expect(orchestration).toContain('Мастер');
    expect(orchestration).toContain('Есть проблемы');
  });

  it('routing-rules.md contains explicit rows for "автоматизация" and "интеграции"', () => {
    const routingRules = fs.readFileSync(path.join(promptMasterDir, 'routing-rules.md'), 'utf8');

    expect(routingRules).toMatch(/\|\s*автоматизация\s*\|/);
    expect(routingRules).toMatch(/\|\s*интеграции\s*\|/);
  });
});
