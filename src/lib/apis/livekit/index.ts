import { LIVEKIT_API_BASE_URL } from '$lib/constants';
import { toast } from 'svelte-sonner';

export const getLivekitToken = async () => {
	const token = localStorage.token;

	const resp = await fetch(`${LIVEKIT_API_BASE_URL}/token`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
	});

	if (!resp.ok) {
		const text = await resp.text();
		throw new Error(`LiveKit token error: ${resp.status} ${text}`);
	}

	try {
		return await resp.json()
	} catch (err) {
		console.error(err);
		toast.error(err as never);
	}
}

