SHELL := /bin/bash

.PHONY: preflight verify verify-bot vpn.audit vpn.deploy vpn.verify vpn.rollback vpn.report ssh.preflight ssh.primary ssh.reserve openclaw.security-profile openclaw.security-updates openclaw.update openclaw.update-permissions openclaw.privileged openclaw.gateway-repair openclaw.healthcheck-schedule openclaw.daily-ops openclaw.next-week-prep openclaw.context-snapshot openclaw.friction-scan openclaw.weekly-focus openclaw.high-leverage openclaw.instruction-conflicts openclaw.session-handoff openclaw.post-change-verify openclaw.ops-intelligence openclaw.model-primary openclaw.whoop-morning-check

preflight:
	chmod +x ./scripts/preflight.sh ./scripts/verify_integrations.sh
	./scripts/preflight.sh

verify:
	chmod +x ./scripts/preflight.sh ./scripts/verify_integrations.sh
	./scripts/verify_integrations.sh
	$(MAKE) verify-bot

verify-bot:
	cd ./bot && npm test && npm run smoke:notifications

vpn.audit:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh audit

vpn.deploy:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./services/subscription/deploy_subscription.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh deploy

vpn.verify:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./checks/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh verify

vpn.rollback:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh rollback

vpn.report:
	chmod +x ./checks/morning_health_report.sh ./checks/vpn_verify.sh
	DRY_RUN=$${DRY_RUN:-1} ./checks/morning_health_report.sh

ssh.preflight:
	chmod +x ./ops/ssh_happ.sh ./checks/check_access.sh
	DRY_RUN=$${DRY_RUN:-1} ./checks/check_access.sh

ssh.primary:
	chmod +x ./ops/ssh_happ.sh
	./ops/ssh_happ.sh primary

ssh.reserve:
	chmod +x ./ops/ssh_happ.sh
	./ops/ssh_happ.sh reserve

openclaw.security-profile:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh security_profile

openclaw.security-updates:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh security_updates $${MODE:-inspect}

openclaw.update:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_update $${MODE:-inspect}

openclaw.update-permissions:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_update_permissions $${MODE:-inspect}

openclaw.privileged:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_privileged_exec $${MODE:-inspect}

openclaw.gateway-repair:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_gateway_repair $${MODE:-inspect}

openclaw.healthcheck-schedule:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_healthcheck_schedule $${MODE:-inspect}

openclaw.daily-ops:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./checks/*.sh ./scripts/verify_integrations.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh daily_ops

openclaw.next-week-prep:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/next_week_prep.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh next_week_prep

openclaw.context-snapshot:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/context_snapshot.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh context_snapshot

openclaw.friction-scan:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/friction_scan.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh friction_scan

openclaw.weekly-focus:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/weekly_focus_review.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh weekly_focus_review

openclaw.high-leverage:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/high_leverage_24h.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh high_leverage_24h

openclaw.instruction-conflicts:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./checks/instruction_conflicts.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh instruction_conflicts

openclaw.session-handoff:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./scripts/session_artifacts.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh session_handoff "$${NOTE:-Автоматический handoff}"

openclaw.post-change-verify:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./checks/*.sh ./scripts/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh post_change_verify

openclaw.ops-intelligence:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh ./checks/*.sh ./scripts/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh ops_intelligence

openclaw.model-primary:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-1} ./infra/orchestrator/run_workflow.sh openclaw_model_primary $${MODE:-inspect} $${MODEL:-openai/gpt-5.3-codex}

openclaw.whoop-morning-check:
	chmod +x ./infra/orchestrator/run_workflow.sh ./infra/orchestrator/lib.sh ./infra/orchestrator/workflows/*.sh
	DRY_RUN=$${DRY_RUN:-0} ./infra/orchestrator/run_workflow.sh whoop_morning_report_check
