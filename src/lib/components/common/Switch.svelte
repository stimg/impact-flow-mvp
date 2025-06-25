<script lang="ts">
	import { createEventDispatcher, tick } from 'svelte';
	import { Switch } from 'bits-ui';
	export let state = true;
	export let id = '';

	const dispatch = createEventDispatcher();

	$: dispatch('change', state);
</script>

<Switch.Root
	bind:checked={state}
	{id}
	class="flex h-5 min-h-5 w-9 shrink-0 cursor-pointer items-center rounded-full px-[3px] mx-[1px] transition
		outline outline-1 disabled:outline-gray-400 disabled:cursor-not-allowed
		{state
		? 'bg-teal-500 dark:bg-teal-600 outline-teal-600 dark:outline-teal-500'
		: 'bg-gray-200 dark:bg-gray-800 outline-gray-300 dark:outline-gray-700'}"
>
	<Switch.Thumb
		class="pointer-events-none block size-4 shrink-0 rounded-full bg-white transition-transform data-[state=checked]:translate-x-3.5 data-[state=unchecked]:translate-x-0 data-[state=unchecked]:shadow-mini "
	/>
</Switch.Root>
