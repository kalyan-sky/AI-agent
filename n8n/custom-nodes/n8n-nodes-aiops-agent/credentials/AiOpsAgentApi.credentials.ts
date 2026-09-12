import type {
	IAuthenticateGeneric,
	ICredentialTestRequest,
	ICredentialType,
	INodeProperties,
} from 'n8n-workflow';

/**
 * Holds the agent-service base URL + API key so no workflow ever embeds
 * a raw key — every node that talks to agent-service references this
 * credential by name instead.
 */
export class AiOpsAgentApi implements ICredentialType {
	name = 'aiOpsAgentApi';

	displayName = 'AI-Ops Agent API';

	documentationUrl = 'https://github.com/kalyan-sky/AI-agent';

	properties: INodeProperties[] = [
		{
			displayName: 'Base URL',
			name: 'baseUrl',
			type: 'string',
			default: 'http://agent-service:8000',
			description: 'Base URL of the running agent-service (no trailing slash)',
		},
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			default: '',
			description: 'One of the keys configured in agent-service via API_KEYS',
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {
				Authorization: '=Bearer {{$credentials.apiKey}}',
			},
		},
	};

	test: ICredentialTestRequest = {
		request: {
			baseURL: '={{$credentials.baseUrl}}',
			url: '/health',
			method: 'GET',
		},
	};
}
