# apps/larisa_ivanovna

## Current status

This is the canonical local source path for the Larisa Ivanovna application code.

Legacy compatibility imports remain available through:

`agents/larisa_ivanovna`

## Boundary

This folder owns Larisa application code:

- agent
- commands
- workflows
- providers
- schemas
- formatters
- policy
- timezone helpers

## Runtime note

Moving code here does not change live server runtime pointers.

Any server/runtime cutover still requires separate approval, smoke validation, and rollback expectation.
