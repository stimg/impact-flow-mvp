<script lang="ts">
	import type { Banner } from '$lib/types';
	import { onMount, createEventDispatcher } from 'svelte';
	import { fade } from 'svelte/transition';
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	const dispatch = createEventDispatcher();

	export let banner: Banner = {
		id: '',
		type: 'info',
		title: '',
		content: '',
		url: '',
		dismissible: true,
		timestamp: Math.floor(Date.now() / 1000)
	};
	export let dismissed = false;

	let mounted = false;

	const classNames: Record<string, string> = {
		info: 'banner-info',
		success: 'banner-success',
		warning: 'banner-warning',
		error: 'banner-error'
	};

	const dismiss = (id: string) => {
		dismissed = true;
		dispatch('dismiss', id);
	};

	onMount(() => {
		mounted = true;
	});
</script>

{#if !dismissed}
	{#if mounted}
		<div
			class="{classNames[banner.type] ?? classNames['info']} top-3 left-0 right-0 p-2 px-3 mx-5
			 flex justify-center items-center relative rounded-md border backdrop-blur-xl z-30"
			transition:fade={{ delay: 100, duration: 300 }}
		>
			<div class=" flex flex-col md:flex-row md:items-center flex-1 text-sm w-fit">
				<div class="flex justify-between self-start">
					{#if banner.url}
						<div class="flex md:hidden group w-fit md:items-center">
							<a
								class="text-xs font-semibold underline"
								href="/assets/files/whitepaper.pdf"
								target="_blank">Learn More</a
							>

							<div
								class=" ml-1 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-white"
							>
								<!--  -->
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 16 16"
									fill="currentColor"
									class="w-4 h-4"
								>
									<path
										fill-rule="evenodd"
										d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
										clip-rule="evenodd"
									/>
								</svg>
							</div>
						</div>
					{/if}
				</div>

				<div class="flex-1 text-sm max-h-20 overflow-y-auto">
					{@html marked.parse(DOMPurify.sanitize(banner.content))}
				</div>
			</div>

			{#if banner.url}
				<div class="hidden md:flex group w-fit md:items-center">
					<a
						class="text-xs font-semibold underline"
						href="/"
						target="_blank">Learn More</a
					>

					<div class=" ml-1 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-white">
						<!--  -->
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 16 16"
							fill="currentColor"
							class="size-4"
						>
							<path
								fill-rule="evenodd"
								d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
								clip-rule="evenodd"
							/>
						</svg>
					</div>
				</div>
			{/if}
			<div class="flex self-start">
				{#if banner.dismissible}
					<button
						on:click={() => {
							dismiss(banner.id);
						}}
						class="-mt-1 -mb-2 translate-y-[1px] ml-1.5 mr-1 text-white hover:text-red"
						>&times;</button
					>
				{/if}
			</div>
		</div>
	{/if}
{/if}
