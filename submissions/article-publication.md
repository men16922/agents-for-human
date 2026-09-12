# AWS Builder Center article preparation

Status: local English draft; no article has been created or published on Builder Center.

- Article: [article.md](article.md).
- Title: **Agents for Humans: Rehearsing an AI Agent’s Purchase Before It Spends**.
- Description: Rehearsal uses Amazon Nova 2 Lite and a serverless AWS workflow to measure transaction plans in isolated worlds and present evidence before a person decides to proceed.
- Suggested topics, subject to the editor’s available choices: agentic AI, Amazon Bedrock, Amazon Bedrock AgentCore, serverless, Amazon DynamoDB.
- Cover candidate: [current impact report](../evidence/preflight/chrome/result.png). The four inline figures reuse actual retained screenshots and the official AWS diagram; no new generated product images are needed.

## Editorial basis

The requested [Builder Center example](https://builder.aws.com/content/3Gcre7M8p0lcazXeIIkykhnhLKN/building-a-safe-event-driven-devops-agent-from-read-only-diagnosis-to-verified-pull-requests) was read through its indexed full article. Its problem-to-design-to-verification progression informed the outline. Rehearsal’s text, scenario and technical claims were written from this repository’s implementation and retained evidence; the example’s DevOps architecture and results are not attributed to this project.

The main factual sources are [the preflight audit](../docs/test/preflight-impact.md), [contracts](../src/rehearsal/preflight/contracts.py), [planner](../src/rehearsal/preflight/planner.py), [simulation](../src/rehearsal/preflight/simulation.py), [report verification](../src/rehearsal/preflight/report.py), [cloud decisions](../src/rehearsal/preflight/cloud.py), and [deployment guide](../infra/serverless/README.md). AWS documentation links appear beside the transaction and session-lifecycle statements they support.

## Before publication

1. Upload the four images using the Builder Center editor and preserve their captions and alt text. Relative Markdown image paths are local assets, not hosted image URLs.
2. Replace local source, evidence and testing links with verified public repository links after Git push succeeds. The configured destination is `https://github.com/men16922/agents-for-human`, but source publication remains blocked by the execution policy recorded in [the Git checkpoint](../docs/test/git-publication.md).
3. Replace the local MP4 link with a verified public video URL after upload. Do not imply the local MP4 is already on YouTube.
4. Check the pasted article, tables, images, links and author profile in the editor. Publish only within an explicit publication request; preparing this article does not submit the Devpost project.
5. After publication, verify anonymous access and enter the resulting article URL in the Devpost bonus-post field. The title already includes “Agents for Humans.”

The article reports the September 12 retained run. It does not assert live remaining budget, current demo availability, prompt-cache savings, authenticated payment approval, production reliability or measured human benefit. No paid model call, cloud mutation or additional video generation was needed to write it.
