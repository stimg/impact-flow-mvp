// TypeScript
import { RECOMMENDATIONS_API_BASE_URL } from '$lib/constants';

export const getRecommendationByTag = async (token: string, tag: string) => {
	let error: string | null = null;

	const res = await fetch(`${RECOMMENDATIONS_API_BASE_URL}/?tag=${encodeURIComponent(tag)}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const processRecommendation = async (
	token: string,
	id: string,
	metadata: Record<string, unknown> = {}
) => {
	let error: string | null = null;

	const res = await fetch(`${RECOMMENDATIONS_API_BASE_URL}/process`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			id,
			metadata
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
