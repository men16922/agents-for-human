# Submission readiness

Deployment and submission checklist refreshed 2026-09-12. The AWS demo is deployed. Submission documents remain drafts; code/video publication and Devpost Submit have not occurred. The official rules below were rechecked on 2026-09-12. The [Nova execution plan](../plans/2026-09-12-nova-live.md) records the approved USD10 model budget and actual costs.

The [official rules](https://agentsforhumans.devpost.com/rules), checked on 2026-09-12, require a public source repository with an MIT/Apache license and README, an architecture diagram, a public YouTube/Vimeo working-demo video of at most five minutes, an AWS Builder ID, English materials or translations, and free judging access to a working project through the end of judging on October 8. Submission closes September 14 at 17:00 PDT (September 15 at 09:00 KST). A hosted demo and AgentCore deployment are optional. This checklist tracks deliverables, not eligibility advice.

| Deliverable | Current evidence | Remaining action |
|---|---|---|
| Working Strands agent | [Actual Nova preflight](../test/preflight-impact.md), twelve isolated runs, independent report, decision export and reload | Real transaction connector, independent prediction validation and user outcomes remain future work |
| English project description | [Project draft](PROJECT.md) | Final measured results reflected; review entrant-facing copy and public links |
| README and testing | [Root README](../../README.md), [English instructions](TESTING.md), tested `make commerce-demo` live inspection | Same-host Linux checks and local free inspection passed; independent-machine reproduction and public judging access remain |
| Architecture | [Deployed diagram and boundaries](ARCHITECTURE.md), editable draw.io and PNG/SVG | Both draw.io pages opened and checked |
| Source license and notices | [MIT](../../LICENSE), [notices](../../THIRD_PARTY_NOTICES.md), [final local package audit](../test/nova-final-submission.md) | Final source package prepared locally; public repository access remains |
| Public code repository | Origin registered at men16922/agents-for-human; no initial commit/push | Publish when requested, then verify anonymous source access |
| Video, at most five minutes | [2:53 English Chrome/AWS/Nova video](../../submissions/video/rehearsal-demo.mp4), direct Chrome walkthrough, actual preflight run, English narration/captions and playback checks | Final results reflected and local playback/captions verified; human review, publication and public-access check remain |
| AWS Builder ID | Not supplied here | Entrant supplies through submission form |
| Comparison evidence | Actual Nova five-case four-arm pilot with complete denominator and recorded provider usage; prior SDK evidence retained separately | Three known pilots and the prospective 80-cell batch audited; independent held-out generalization and billing reconciliation remain |
| User value | Pre-execution evidence for a family shopping decision | Measure decision quality with users before claiming reduced losses or time saved |
| Hosted demo | [Live AWS demo](https://d1u9yhii3gor6j.cloudfront.net), [preview audit](../test/preflight-impact.md), actual Nova planning, synthetic simulations, decision and session absence | Finite shared allowance; monitor through judging without resetting it automatically |
| Final submission | Not submitted | Cross-check actual links and submit when requested |

The project is not submission-ready merely because the local documentation or test gate passes. A local draft video now exists; actual model results are recorded, while public source/video links and entrant information remain pending. No credentials should be placed in these drafts.

The earlier [local requirement and artifact audit](../test/readiness-audit.md) checked 250 retained artifacts, 51 relative links and a private source snapshot. It does not establish real-model results, independent reproduction or public judging access.

The [preflight audit](../test/preflight-impact.md) records the current product and artifacts. Earlier model comparisons and packages remain historical evidence. The preflight work is complete within its stated POC scope; public code/video publication, entrant details and final submission remain separate.
