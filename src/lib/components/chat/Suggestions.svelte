<script lang="ts">
    import Fuse from 'fuse.js';
    import Bolt from '$lib/components/icons/Bolt.svelte';
    import { /*onMount,*/ getContext, createEventDispatcher } from 'svelte';
    // import { settings, WEBUI_NAME } from '$lib/stores';
    // import { WEBUI_VERSION } from '$lib/constants';

    const i18n = getContext('i18n');
    const dispatch = createEventDispatcher();

    export let suggestionPrompts = [];
    export let className = '';
    export let inputValue = '';

    let sortedPrompts = [];
    let carouselContainer;
    let isMobile = false;

    // Check if device is mobile
    $: if (typeof window !== 'undefined') {
        isMobile = window.innerWidth <= 768;
    }

    const fuseOptions = {
        keys: ['content', 'title'],
        threshold: 0.5
    };

    let fuse;
    let filteredPrompts = [];

    // Initialize Fuse
    $: fuse = new Fuse(sortedPrompts, fuseOptions);

    // Update the filteredPrompts if inputValue changes
    // Only increase version if something wirklich geändert hat
    $: getFilteredPrompts(inputValue);

    // Helper function to check if arrays are the same
    // (based on unique IDs oder content)
    function arraysEqual(a, b) {
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i++) {
            if ((a[i].id ?? a[i].content) !== (b[i].id ?? b[i].content)) {
                return false;
            }
        }
        return true;
    }

    const getFilteredPrompts = (inputValue) => {
        if (inputValue.length > 500) {
            filteredPrompts = [];
        } else {
            const newFilteredPrompts =
                inputValue.trim() && fuse
                    ? fuse.search(inputValue.trim()).map((result) => result.item)
                    : sortedPrompts;

            // Compare with the oldFilteredPrompts
            // If there's a difference, update array + version
            if (!arraysEqual(filteredPrompts, newFilteredPrompts)) {
                filteredPrompts = newFilteredPrompts;
            }
        }
    };

    $: if (suggestionPrompts) {
        sortedPrompts = [...(suggestionPrompts ?? [])].sort(() => Math.random() - 0.5);
        getFilteredPrompts(inputValue);
    }
</script>

<div class="mb-3 flex gap-1 text-xs font-medium items-center text-gray-600 dark:text-gray-400">
    {#if filteredPrompts.length > 0}
        <Bolt />
        {$i18n.t('Suggested')}
    {/if}
</div>

<div class="w-full mb-5">
    {#if filteredPrompts.length > 0}
        <!-- Desktop/Tablet Grid Layout -->
        <div class="hidden md:grid grid-cols-2 gap-3 max-h-35 overflow-auto scrollbar-none {className}">
            {#each filteredPrompts as prompt, idx (prompt.id || prompt.content)}
                <button class="waterfall w-auto px-3 py-2 rounded-md border bg-gray-50 border-gray-200 dark:bg-gray-850 dark:border-gray-800
				hover:bg-gray-100 dark:hover:bg-black/5 dark:hover:bg-white/5 transition group"
                        style="animation-delay: {idx * 60}ms" on:click={() => dispatch('select', prompt.content)}>
                    <div class="text-left">
                        {#if prompt.title && prompt.title[0] !== ''}
                            <div
                                    class="font-medium dark:text-gray-300 dark:group-hover:text-gray-200 transition line-clamp-1"
                            >
                                {prompt.title[0]}
                            </div>
                            <div class="text-xs text-gray-600 dark:text-gray-400 font-normal line-clamp-1">
                                {prompt.title[1]}
                            </div>
                        {:else}
                            <div
                                    class="font-medium dark:text-gray-300 dark:group-hover:text-gray-200 transition line-clamp-1"
                            >
                                {prompt.content}
                            </div>
                            <div class="text-xs text-gray-600 dark:text-gray-400 font-normal line-clamp-1">
                                {$i18n.t('Prompt')}
                            </div>
                        {/if}
                    </div>
                </button>
            {/each}
        </div>

        <!-- Mobile Carousel Layout with Fade Effect -->
        <div class="md:hidden mobile-carousel-wrapper relative">
            <!-- Left fade overlay -->
            <div class="carousel-fade-left absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-white dark:from-gray-900 to-transparent z-10 pointer-events-none"></div>

            <!-- Right fade overlay -->
            <div class="carousel-fade-right absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-white dark:from-gray-900 to-transparent z-10 pointer-events-none"></div>

            <div
                    class="mobile-carousel-container overflow-x-auto scrollbar-none"
                    bind:this={carouselContainer}
            >
                <div class="mobile-carousel flex gap-3 px-6">
                    {#each filteredPrompts as prompt, idx (prompt.id || prompt.content)}
                        <button
                                class="waterfall mobile-prompt-card flex-shrink-0 px-4 py-3 rounded-lg border bg-gray-50 border-gray-200 dark:bg-gray-850 dark:border-gray-800
							hover:bg-gray-100 dark:hover:bg-black/5 dark:hover:bg-white/5 transition group"
                                style="animation-delay: {idx * 60}ms"
                                on:click={() => dispatch('select', prompt.content)}
                        >
                            <div class="text-left whitespace-nowrap">
                                {#if prompt.title && prompt.title[0] !== ''}
                                    <div class="font-medium dark:text-gray-300 dark:group-hover:text-gray-200 transition">
                                        {prompt.title[0]}
                                    </div>
                                    <div class="text-xs text-gray-600 dark:text-gray-400 font-normal">
                                        {prompt.title[1]}
                                    </div>
                                {:else}
                                    <div class="font-medium dark:text-gray-300 dark:group-hover:text-gray-200 transition">
                                        {prompt.content}
                                    </div>
                                    <div class="text-xs text-gray-600 dark:text-gray-400 font-normal">
                                        {$i18n.t('Prompt')}
                                    </div>
                                {/if}
                            </div>
                        </button>
                    {/each}
                </div>
            </div>
        </div>
    {/if}
</div>

<style>
    /* Waterfall animation for the suggestions */
    @keyframes fadeInUp {
        0% {
            opacity: 0;
            transform: translateY(20px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .waterfall {
        opacity: 0;
        animation-name: fadeInUp;
        animation-duration: 200ms;
        animation-fill-mode: forwards;
        animation-timing-function: ease;
    }

    /* Mobile carousel wrapper */
    .mobile-carousel-wrapper {
        position: relative;
    }

    /* Mobile carousel styles */
    .mobile-carousel-container {
        scroll-behavior: smooth;
        -webkit-overflow-scrolling: touch;
        scroll-snap-type: x mandatory;
    }

    .mobile-prompt-card {
        scroll-snap-align: start;
        min-width: fit-content;
        max-width: 85vw;
    }

    .mobile-carousel {
        padding-bottom: 2px; /* Prevent cut-off shadow/border */
    }

    /* Fade overlays */
    .carousel-fade-left,
    .carousel-fade-right {
        width: 24px;
        opacity: 0.8;
        transition: opacity 0.3s ease;
    }

    /* Enhanced fade effect for better visibility */
    .carousel-fade-left {
        background: linear-gradient(
                to right,
                rgb(255, 255, 255) 0%,
                rgba(255, 255, 255, 0.8) 40%,
                rgba(255, 255, 255, 0.4) 70%,
                transparent 100%
        );
    }

    .carousel-fade-right {
        background: linear-gradient(
                to left,
                rgb(255, 255, 255) 0%,
                rgba(255, 255, 255, 0.8) 40%,
                rgba(255, 255, 255, 0.4) 70%,
                transparent 100%
        );
    }

    /* Dark mode fade overlays */
    :global(.dark) .carousel-fade-left {
        background: linear-gradient(
                to right,
                rgb(17, 24, 39) 0%,
                rgba(17, 24, 39, 0.8) 40%,
                rgba(17, 24, 39, 0.4) 70%,
                transparent 100%
        );
    }

    :global(.dark) .carousel-fade-right {
        background: linear-gradient(
                to left,
                rgb(17, 24, 39) 0%,
                rgba(17, 24, 39, 0.8) 40%,
                rgba(17, 24, 39, 0.4) 70%,
                transparent 100%
        );
    }

    /* Custom scrollbar hiding for mobile */
    .mobile-carousel-container::-webkit-scrollbar {
        display: none;
    }

    .mobile-carousel-container {
        -ms-overflow-style: none;
        scrollbar-width: none;
    }

    /* Smooth snap effect */
    @media (max-width: 768px) {
        .mobile-carousel-container {
            scroll-snap-type: x proximity;
        }

        .mobile-prompt-card {
            scroll-snap-align: center;
        }
    }
</style>
