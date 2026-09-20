### Key points to discuss

- **Term 2 direction**
    - We are moving from a research-heavy project toward a **working BESS planning software tool**.
    - The target is a program that can simulate a small distribution system, starting around **5 buses**, then later validate on **IEEE 33-bus**.
    - The software should eventually perform **BESS sizing and placement optimization under renewable/load uncertainty**.
- **Main weakness from Term 1**
    - We had many technical pieces: ARIMA, Monte Carlo, GWO, BESS model concepts, power flow, IEEE 33-bus.
    - But they were not connected into a complete **engineering design + implemented system**.
    - Term 2 needs to focus on architecture, interfaces, implementation, testing, and validation.
- **Immediate priority: DATA**
    - Advisors asked us to get data before the next meeting.
    - This week we need to collect:
        - historical **load-demand data**,
        - **PV / irradiance / weather data**,
        - **distribution-network data** for a small test system and IEEE 33-bus,
        - later, BESS/economic parameters.
    - For every dataset, record:
        - source,
        - units,
        - time resolution,
        - date range,
        - missing data,
        - whether it can legally/academically be used.
- **What we should have before the advisor meeting**
    - Actual downloaded datasets, not only links.
    - A few sample plots.
    - Short explanation of what each dataset contains.
    - Any quality/problems we found.
    - Questions for the advisors if we need approval between multiple dataset options.
- **Data preprocessing**
    - Load and renewable data need compatible timestamps and resolution.
    - We should decide whether our main simulation resolution will be hourly or something else.
    - Document all cleaning/resampling steps so we can reproduce them later.
- **Ethics / professional responsibility**
    - This is now an early priority, not something to write only at the end.
    - Main points include:
        - data integrity and proper sourcing,
        - transparent assumptions,
        - clearly stating model limitations,
        - grid reliability/safety implications,
        - environmental/economic trade-offs,
        - not presenting optimizer output as a guaranteed real-world decision.
- **Next design discussion**
    - After the data task, we need to confirm the **minimum product scope**:
        - what the user can input,
        - what network sizes are supported,
        - what BESS variables are optimized,
        - how uncertainty enters the optimization,
        - what the program outputs.

### Suggested decisions to leave the meeting with
1. Who is responsible for **load data**.
2. Who is responsible for **PV/weather data**.
3. Who is responsible for **network / IEEE 33-bus data**.
4. Agreed minimum requirements for acceptable datasets.
5. Whether we aim for **hourly data** as the initial common resolution.
6. What evidence each person must bring before the next team/advisor meeting.
