import {
	NodeApiError,
	NodeConnectionTypes,
	NodeOperationError,
	type IDataObject,
	type IExecuteFunctions,
	type INodeExecutionData,
	type INodeType,
	type INodeTypeDescription,
	type JsonObject,
} from 'n8n-workflow';

/**
 * Calls agent-service's POST /api/v1/agent/run — the same endpoint the
 * REST API exposes directly. This node exists so an n8n workflow can
 * invoke the agent without a raw HTTP Request node (schema-validated
 * inputs, structured error handling, and a credential type instead of a
 * hardcoded key/URL in every workflow that needs it).
 */
export class AiAgentExecute implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'AI Agent Execute',
		name: 'aiAgentExecute',
		icon: 'fa:robot',
		group: ['transform'],
		version: 1,
		description: 'Run the AI-Ops incident-investigation agent on a message',
		defaults: {
			name: 'AI Agent Execute',
		},
		inputs: [NodeConnectionTypes.Main],
		outputs: [NodeConnectionTypes.Main],
		credentials: [
			{
				name: 'aiOpsAgentApi',
				required: true,
			},
		],
		properties: [
			{
				displayName: 'Conversation ID',
				name: 'conversationId',
				type: 'string',
				default: '',
				required: true,
				description: 'Stable ID for this conversation — reused across turns for memory continuity',
			},
			{
				displayName: 'User ID',
				name: 'userId',
				type: 'string',
				default: '',
				required: true,
			},
			{
				displayName: 'Message',
				name: 'message',
				type: 'string',
				typeOptions: { rows: 3 },
				default: '',
				required: true,
				description: 'The incident description or question to investigate',
			},
			{
				displayName: 'Timeout (ms)',
				name: 'timeoutMs',
				type: 'number',
				default: 100000,
				description:
					"Should exceed agent-service's own AGENT_TIMEOUT_S so the agent's own timeout fires first",
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];

		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			const conversationId = this.getNodeParameter('conversationId', itemIndex) as string;
			const userId = this.getNodeParameter('userId', itemIndex) as string;
			const message = this.getNodeParameter('message', itemIndex) as string;
			const timeoutMs = this.getNodeParameter('timeoutMs', itemIndex) as number;

			if (!conversationId.trim() || !userId.trim() || !message.trim()) {
				throw new NodeOperationError(
					this.getNode(),
					'conversationId, userId, and message are all required and cannot be blank',
					{ itemIndex },
				);
			}

			const credentials = await this.getCredentials('aiOpsAgentApi');

			try {
				const response = (await this.helpers.httpRequestWithAuthentication.call(
					this,
					'aiOpsAgentApi',
					{
						baseURL: credentials.baseUrl as string,
						url: '/api/v1/agent/run',
						method: 'POST',
						body: {
							conversation_id: conversationId,
							user_id: userId,
							message,
						},
						json: true,
						timeout: timeoutMs,
					},
				)) as IDataObject;

				returnData.push({ json: response, pairedItem: { item: itemIndex } });
			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({
						json: { error: (error as Error).message },
						pairedItem: { item: itemIndex },
					});
					continue;
				}

				const message_ = (error as Error).message ?? '';
				const isTimeout = /timeout|timed out|ETIMEDOUT|ECONNABORTED/i.test(message_);
				throw new NodeApiError(this.getNode(), error as JsonObject, {
					message: isTimeout
						? `agent-service did not respond within ${timeoutMs}ms`
						: `agent-service request failed: ${message_}`,
					itemIndex,
				});
			}
		}

		return [returnData];
	}
}
