#main
async def main(backtest_period: int, output: str):
    # Use the pre-configured logger from earlier in the script.
    logger.info("Starting the main function.")

    config = Config("config.ini")
    backtest = Backtest()
    categories = config.get_categories()
    timeout = ClientTimeout(total=60)
    output_format = config.get_output_format()
    filename = f"results.{output_format}"

    cache = Cache(LRUCache(CACHE_SIZE))
    cache_manager = CacheManager(cache)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        projector = PointsProjector(config, session)
        schedule_processor = ScheduleProcessor()

        schedule = await schedule_processor.get_schedule(session, backtest_period)
        team_ranks_list = await fetch_and_extract_team_ranks(
            session, config, schedule, categories, cache_manager
        )

        scoring_keys = [
            key.lower().replace("%%", "") for key in config.scoring_criteria().keys()
        ]
        validated_ranks_list = [
            TeamRankingExtractor().validate_ranks(ranks, scoring_keys)
            for ranks in team_ranks_list
        ]

        paired_ranks = [
            {"home": validated_ranks_list[i], "away": validated_ranks_list[i + 1]}
            for i in range(0, len(validated_ranks_list), 2)
        ]

        projections = await projector.calculate_projections(
            schedule["matchups"], config.scoring_criteria(), paired_ranks
        )

        win_rate = backtest.backtest_model(projections, {})
        print(f"Win Rate: {win_rate * 100:.2f}%")
        logger.info(f"Projections: {projections}")

        if not projections:
            logger.warning("Projections list is empty. No data to save.")
            return

        logger.info(f"Attempting to save {len(projections)} projections to {filename}.")

        writer = DataWriter.infer_writer(filename)
        try:
            writer.write_data(projections, filename)
            logger.info(f"Results successfully saved to {filename}")
        except (DataWriterError, ClientError, IOError) as e:
            logger.error(
                f"Failed to save results to {filename}. Error: {e}", exc_info=True
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)

        print(f"Check logs for details on saving results to {filename}")
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process schedules and predictions.")
    parser.add_argument(
        "--backtest_period", type=int, default=1, help="Number of days to backtest."
    )
    parser.add_argument("--output", type=str, help="Output file path.", required=True)
    args = parser.parse_args()

    asyncio.run(main(args.backtest_period, args.output))