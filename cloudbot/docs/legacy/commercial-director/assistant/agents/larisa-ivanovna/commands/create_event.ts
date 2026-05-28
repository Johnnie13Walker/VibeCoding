import { LARISA_COMMAND_ALIASES, larisaIvanovnaConfig } from "../config";
import type { CreateCalendarEventInput } from "../schemas/calendar.schema";
import {
  runCreateEventWorkflow,
  type CreateEventWorkflowDeps,
} from "../workflows/create_event.workflow";

type CreateEventCommandInput = Partial<Omit<CreateCalendarEventInput, "timezone">> & {
  timezone?: CreateCalendarEventInput["timezone"];
  start_at?: string;
  end_at?: string;
  join_url?: string;
};

function normalizeCreateEventInput(input: CreateEventCommandInput): CreateCalendarEventInput {
  const {
    start_at,
    end_at,
    join_url,
    startAtMsk,
    endAtMsk,
    joinUrl,
    ...rest
  } = input;

  return {
    ...rest,
    title: rest.title ?? "",
    startAtMsk: startAtMsk ?? start_at ?? "",
    endAtMsk: endAtMsk ?? end_at,
    joinUrl: joinUrl ?? join_url,
  };
}

export function createCreateEventCommand(deps: CreateEventWorkflowDeps) {
  return {
    name: "create_event",
    aliases: [
      ...LARISA_COMMAND_ALIASES.createEvent,
      ...larisaIvanovnaConfig.legacyCommandAliases.createEvent,
    ],
    async execute(input: CreateEventCommandInput = {}) {
      const result = await runCreateEventWorkflow(normalizeCreateEventInput(input), deps);

      return {
        text: result.text,
        payload: result,
      };
    },
  };
}
