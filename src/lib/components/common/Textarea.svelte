<script lang="ts">
	import { onMount, tick } from 'svelte';

	export let className = 'rounded-lg px-3.5 py-2 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden';
	export let value = '';
	export let placeholder = '';
	export let rows = 1;
	export let minSize = null;
	export let required = false;
	export let maxlength = null;
	export let onKeydown: ((event: KeyboardEvent) => void) | null = null;
	export let onKeyup: ((event: KeyboardEvent) => void) | null = null;
	export let onInput: ((event: KeyboardEvent) => void) | null = null;

	let textareaElement: HTMLTextAreaElement;

	// Adjust height on mount and after setting the element.
	onMount(async () => {
		await tick();
		resize();

		requestAnimationFrame(() => {
			// setInterveal to cehck until textareaElement is set
			const interval = setInterval(() => {
				if (textareaElement) {
					clearInterval(interval);
					resize();
				}
			}, 100);
		});
	});

	const resize = () => {
		if (textareaElement) {
			textareaElement.style.height = '';
			textareaElement.style.height = minSize
				? `${Math.max(textareaElement.scrollHeight, minSize)}px`
				: `${textareaElement.scrollHeight}px`;
		}
	};
</script>

<textarea
	bind:this={textareaElement}
	bind:value
	{placeholder}
	class={className}
	style="field-sizing: content;"
	rows="{rows}"
	maxlength="{maxlength}"
	{required}
	on:input={(e)=> {
		if (onInput) {
			onInput(e);
		}
		resize();
	}}
	on:focus={() => {
		resize();
	}}
	on:keydown={onKeydown}
	on:keyup={onKeyup}
/>
