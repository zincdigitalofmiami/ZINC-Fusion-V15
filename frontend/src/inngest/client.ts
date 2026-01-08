import { Inngest } from "inngest";

const eventKey = process.env.INNGEST_EVENT_KEY ?? process.env.WORKFLOW_INNGEST_EVENT_KEY;
const signingKey = process.env.INNGEST_SIGNING_KEY ?? process.env.WORKFLOW_INNGEST_SIGNING_KEY;

export const inngest = new Inngest({
	id: "fusion-jobs",
	eventKey,
	signingKey,
});
