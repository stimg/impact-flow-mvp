import { QNA_API_BASE_URL } from '$lib/constants';

export const getQNAByName = async (
	token: string,
	question: string,
) => {
	let error = null;

	const res = await fetch(`${QNA_API_BASE_URL}/?question=${encodeURIComponent(question)}`, {
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

export const processQNA = async (
	token: string,
	id: string,
	metadata = {},
) => {
	let error = null;

	const res = await fetch(`${QNA_API_BASE_URL}/process`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},

		body: JSON.stringify({
			id,
			metadata,
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

