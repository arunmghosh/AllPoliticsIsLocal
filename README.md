# All Politics Is Local
An interactive election simulation game in which you run for office and progress to higher positions as you win and gain more experience. You have a fifty year career timeline in which to reach the presidency. Lose an election, and you lose the game. You also have the option to simulate prior election data to get an idea of how districts vote and select where / with what party you want to run. 

## 1. Gameplay Walkthrough
### a) Data Before Runtime
Prior to running the game, this project stores .txt files with candidate names in the "names" subfolder. The "out_parties.txt" file contains a list of 2500 random names to use for candidates in opposing parties. Similarly, the "in_party.text" file contains a list of 500 names to use for candidates in your party. There is also a "parties.txt" file that has 8 party names.

### b) Initializing The Nation
When the game loads, you are asked to set up the country for which you are simulating elections. You enter a name for it, and then the skeleton is constructed. 

#### Structure of Government
For simplicity, this simulation enforces a strict hierarchy among levels of office: 
1. Nation
2. State
3. City
4. District

The nation contains 50 states, each state contains 10 cities, each city contains 40 districts. 

There are also three different levels of government:
1. Federal (President, Senate, House of Representatives)
2. State (Governor, State Legislature)
3. Local (Mayor, City Council)

The entire nation votes for the President, each state elects a Governor and 3 Senators, each city elects a Mayor and 1 member of the House of Representatives, and each district elects a member of the State Legislature and a member of the City Council. 

Here is the scope and term length for each position:
- President: Elected by entire nation, 8 year term
- Governors & Senators: Elected by a state, 6 year term
- Mayors & House Members: Elected by a city, 4 year term
- State Legislators & City Council Members: Elected by a district, 2 year term

A president can only serve one term, but there no term limits imposed on other positions. 

#### Representation of Politics
Politics is represented by a set of issues, with each have an ideology spectrum represented by the interval (0,1). Specifically, the numbers can range from 0.01 to 0.99 in increments of 0.01. Low numbers mean a conservative position on the issue, while high numbers mean a liberal position. You have the option to choose up to 3 issues to use for the simulation. Those issues can be custom or chosen from a list of suggestions. 

These issues are debated by parties. Each party has a platform, which is a vector of positions taken on issues. The positions can either be 0.25 (mean of conservative values) or 0.75 (mean of liberal values). Each party must have a unique platform, so if there are I issues, there will be 2^I parties. 

All parties nominate a candidate to run for every position. Candidates each have their own platform, sampled from a random distribution with the rule that they must be liberal or conservative on the same issues that their party is. The conservative range is (0,0.5), and the liberal range is (0.5,1). 

Candidates are elected by people, who each belong to the nation, a state, a city and a district. Instead of each person having their own position vector, each district uses its own position vector to split 10,000 votes among the candidates. 

#### Creation of Position Vectors
After you enter the name for the nation, position vectors of each district are generated using the following algorithm:
1. Every state is given a random position vector with each position drawn randomly from (0,1)
2. Every city within each state is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak (highest probability) at the position of the state
3. Every district with each city is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak at the position of the city

The reason this project is called "All Politics Is Local" is because only the district position vectors actually matter for voting. All higher level results are just sums of district results. 

### c) Customizing Your Character
Once the position vectors for all districts are generated, you create your candidate profile. You enter a name, and then get to view the position vectors of all 50 states so you can pick your home state according to the platform you want. Then, you get to view all the cities in that state, pick a home city, and finally, choose a home district. Your first election of the game is the city council race for the district you choose.

### d) Historical Simulation
Before you explicitly choose your platform, you have the option to request historical data to get an idea of which parties occupied each of seats you may be running for the in the game and for how long. This can help inform your choice of platform to maximizing your chances of being elected.  

#### Election Cycles
Elections are held every two years, called a *cycle*. All of the district level positions are up for reelection every cycle. Mayors and members of the House of Representatives serve for two cycles. However, their elections are offset by one cycle. In odd cycles, Mayors are up for election, and in even cycles, house members are up for election. Governors and Senators serve for three cycles, but there are three waves so some are always up for re-election in a given cycle. Split the 50 states into three groups (A, B, C). In cycle 1, group A holds elections for Governor. In cycle 2, group B holds gubernatorial elections, and group C's turn is in cycle 3. Since there are three senators in each state, just assign each one of them a wave (A, B or C) to have their election. Lastly, there is only one President, who serves for four cycles.  

#### Historical Data Format
The results (per cycle) in the historical data are what would be most informative for your decisions in the game:

- "President": Party index
- "Senators": 1D array of 3 party indices
- "House": Party index
- "Governor": Party index
- "State Legislature": Party index
- "Mayor": Party index
- "City Council": Party index

In essence, you only care about the data from where you are trying to run, so you can tune your platform and maximize the chances of being elected. The ultimate goal is to become president, so you need the presidential election trends. Along the way to becoming president, you may hold a number of other offices, but those are specific to one state, one city, and one district, so you don't need to keep track of another other areas. You won't know in advance what Senate cycle you will fall into, so all three seats from your state are tracked just in case. 

This data is written to a spreadsheet called "historical_data.xlsx" in the "data" subfolder, where the fields in quotation marks are table headers and each row is a cycle of data (the party of the incumbent holding that office for that cycle). The three senate seats can be treated as three separate columns. 

#### How Historical Simulation Works
As mentioned before, this simulation doesn't count individual votes, since that is computationally expensive. For historical simulation data, you only see the winning party for each position of interest for each cycle. Thus, for each race you get data on, the program generates a probability distribution for each party in a given race, and randomly picks the winner. The candidates copy the party platforms exactly to save time, and are not assigned names. 

We know that each state, city, and district has a position vector, and so does each party. Initialize the national position vector as 0.5 on all issues. Compute the Euclidean distances between the population (nation, state, city, or district) position and each party platform. A population is most likely to elect the party closest to their ideology (i.e., the party with the smallest distance from them). Take the reciprocals of these distances (plus a smoothing term to avoid divide by zero) so a higher score corresponds to a higher probability of being elected. Standardize these new scores to get a probability distribution.

#### Natural Party Preference Oscillation Mechanism
In real life, the party in power is often blamed for things that go wrong, and may experience a backlash in the next election. To capture this effect in the historical data, population position vectors will dynamically adjust ahead of each cycle depending on who their incumbent politicians are. The "backlash" is a shift away from the status quo. The status quo is modeled as:

- Nation: Position vector of the president
- States: Compute average position vector of the governor and 3 senators
- Cities: Compute average position vector of the mayor and house member
- Districts: Compute average position vector of the state legislator and city council member

On each issue, the population shifts 0.01 from the status quo value of that issue. However, the shift cannot take the position outside the range of 0.01 and 0.99 (if it would, there is no shift).

### e) Present Day Elections
After viewing the historical data (if you requested it), you enter your platform and begin your first election. At that moment, we start to assign names to candidates (see below).

#### Senority
As I mentioned before, the ultimate objective of the game is to be elected president. However, you don't necessarily "level up" immediately after each election you win. There are three things that determine whether or not you can run for a higher office after you win an election: vacancies in higher offices, seniority, and victory size (the tie breaker). A vacancy is an office that your party doesn't hold or plans to vacate so the incumbent can run for a higher office. Seniority is the number of years a politician has served in a specific office. Lastly, victory size is the percentage of the vote an incumbent received in their latest election. 

The system of seniority functions via the tier of offices shown here:

1. President (not factored into seniority because you can only serve one term, plus you win the game if you become president)
2. Governors (the most senior governor at the time of a presidential election becomes the nominee for president)
3. Senators (the most senior senator from a state becomes nominee for governor of the state if there is a vacancy)
4. House Members (the most senior house members from a state are assigned to run for vacancies in the Senate seats for that state)
5. Mayors (the most senior mayors in a state are are assigned to run for vacant house seats for that state)
6. State Legislators (the most senior state legislator from a city becomes nominee for mayor if there is a vacancy)
7. City Council Members (the most senior city council members are assigned to run for vacancies in the State Legislature for their district)

This system is only practiced by your party, since (for the purposes of this simulation) it doesn't matter what the names of opposing candidates are. If there are no politicians from your party at a specific tier to fill a vacancy, a politician from a lower tier run to fill it (for example, if there are no governors in your party, the most senior Senator from your party runs for president). 

The flow of events that occur between an election victory and running for the next office up the ladder is:

1. Suppose you won an election for tier T in cycle C 
2. In cycle C + 1, your party finds V vacancies for tier T + 1
3. If you are one of the V most senior politicians at tier T, you are assigned to run for one of those vacancies
4. If you are not selected to run, check if you are up for reelection

#### Naming Candidates In Your Party
At the time of your first election, the following politicians are assigned a name from "in_party.txt" if they are in your party:

- Incumbent president
- Incumbent governors
- Sitting senators 
- Sitting house members of your state
- Incumbent mayors in your state
- Sitting state legislators from your city
- City council candidates from your city (for the game, assume all these seats are vacant when you start)

These candidates are all added to "seniority.xlsx" in the data subfolder. The column headers are "Name", "Level of Office", "Seniority", and "Victory Size". The level of office is a number (1 for president through 7 for city council as shown above). In seniority, use the data from "historical_data.xlsx" to determine the number of consecutive years, ending now, that the office has been held by your party, and enter that number. Since we didn't track vote counts for historical elections, put 0 in victory size. 

This list is updated every cycle for which you are still in the game, naming and adding new candidates from your party that win the positions above, and removing candidates who lose. If you keep winning, you will see yourself rise up the list. 

#### Election Night Live: What You See
The default election simulation mode is the mode outlined for generating historical data (see above). However, there is also a live mode that lets you see election results for the current cycle as they come in. The elections that you see in live mode are the elections for seats of the current tier you are running for or currently occupy (if you are not up for reelection or chosen to vacate to run for higher office). Here is a breakdown of which races are in your live scope:

| Office Running For And/Or Hold | Elections Reported To You |
| --- | --- |
| President | Presidential Election |
| Governor | Gubernatorial Elections |
| Senate | Senate Election In Your State |
| House | House Elections In Your State |
| Mayor | Mayoral Elections In Your State |
| State Legislator | State Legislature Elections In Your City |
| City Council | City Council Elections In Your City |

If you are running for an office in a given cycle, that election will always be reported to you live. For all elections reported to you live, every candidate in it has a name, drawn from the appropriate text file if they don't already have one. No duplicate names are allowed. Since opposing candidates also run for a fixed office for simplicity, draw fresh names for your opponents every time you level up, but use the same names if you are running for reelection or watching the same set of elections. Names within your party are recyclable (with the suffix 2, 3, etc if it is drawn that many times). Name drawings are not random. The names are shuffled once at the beginning of the game, and then drawn in order (pointers keep track of where you left off). When you draw all the names in "in_party.txt", loop back to the beginning and increment the suffix. There should be plenty of names for the opponents, so you will never need to recycle. 

When you watch election results on election night, you don't get the full result at once. You see votes trickle in until a winner is able to be called. To simulate this, live elections are done in 10 batches of 1000 votes each at the district level (sum results from districts to get results for higher offices). Here is the process for getting the live vote counts: 

1. Compute a probability distribution over the candidates
2. Generate random slices of the interval (0,1) to slice it, and give one slice to each candidate
3. Multiply the length of a candidate's slice by that candidate's share of the distribution in step 1
4. Standardize the new lengths to get that candidate's share of the vote
5. Multiply each share by the number of rounds of voting (determined by the number of candidates

Let's walk through those steps in more detail. 

The first step is the same as in the default mode, except we create a probability distribution over the candidates instead of the parties. Whenever a candidate is instantiated, they are assigned a permanent position vector for the game, drawn randomly (following the liberal and conservative views of their party). You will be able to tweak your own position vector, within your party range, every time you are up for election. 

Assume that there are P parties, so there are P candidates in every election. We want to randomly divide the interval (0,1) into P slices. To do this, we generate P numbers between 0.8/P and 1.2/P. Standardize the scores so they sum to 1, and give one to each candidate.

But, these scores are completely random and not related to their actual chances of being elected. Thus, we rescale a candidate's score by multiplying it by the candidate's chance of being elected (computed in step 1). 

Since this operation perturbed the probability distribution, we need to standardize the scores again to arrive at the final shares of the vote. For elections with a larger scope than 1 district, these shares are summed over all districts participating in those elections (every district has the same population by design) and standardized one final time.

If there are only 2 parties, then the winner will have at least 50% of the vote. But this system also works for ranked-choice voting. This simulation doesn't actually do multiple rounds or have voters rank candidates. It simulates one round, gets the shares, and multiplies by the number of rounds so the winner is guaranteed to have at least 50%. This represents that over all rounds, at least 50% of voters chose that candidate for one of the rounds. The number of rounds R is determined by P, according to the function R(P) = floor(P/2).

Additionally, "historical_data.xlsx" will be updated with a new row for each cycle in which the user is playing the game. Due to the all politics is local rule, this live simulation method ignores any effects that the actions that higher level politicians have on the voting decisions of people in the district. This means that, for live elections, the Natural Party Preference Oscillation Mechanism only applies to districts. Races not monitored live will be simulated in the default way for speed, and the mechanism will apply to any population level. No races that are not monitored live or tracked in "historical_data.xlsx" will ever be simulated, which makes sense because people generally only care about elections in which they personally voted or those that get national press coverage. 

To ensure that you are not shown everything at once, you are prompted to continue every time a batch is completed, so you can view the results at your own pace. 

#### Updating Seniority
Every cycle, "seniority.xlsx" has to be updated. Candidates who lost their elections will be removed from the list. Candidates who won elections will update their victory size field. Candidates who moved up a tier will update that field and set their seniority to 0. Candidates who were not up for election add 2 to their seniority. New candidates who were not already on the list but won relevant elections (see 'Naming Candidates In Your Party') are named if they did not already have a name, and added to the list with the appropriate tier, 0 seniority, and their victory size. 

#### Your Political Career
Here is the general workflow for each cycle:

1. Determine vacancies, review seniority to see if you are eligible to advance (if not, determine if you are up for reelection or not)
2. If you are running for a higher office or for reelection, you have a chance to tweak your platform within the party bounds
3. Voting (whether or not you are running, you see live returns from select races specified in 'Election Night Live: What You See')
4. If you lost an election, you lose the game
5. If you won or weren't up for an election, update seniority

The game has a 25-cycle (50-year) time limit from when you start. Cycle 1 is the first year of the historical data, and you can simulate all way through Cycle 50 before you start. Suppose you start at Cycle 51. The ultimate objective is to be elected president in Cycle 75 or earlier. If you lose any election, you lose the game. If you are not elected president by the end of Cycle 75, you also lose. This is why it's important that you pick a path (district, city, state) with similar position vectors. You can't change your party once you set your positions, so you want those population position vectors to be within your party range. Lastly, the average of the entire nation is close to 0.5 for each position, so you want to pick moderate positions to maximize your chances of winning that race. Once you finish the game, you have the option to save the results or discard them. If you choose to save the results, the contents of the data subfolder are moved to into the results subfolder, into a subfolder of results with a date/time stamp. The data subfolder is always wiped clean to prepare for the next game. 

## 2. Codebase Architecture
```
AllPoliticsIsLocal/
├── names/                    # Lists of names used for parties and candidates
│   ├── parties.txt           # 8 political party names
│   └── in_party.txt          # 500 candidate names (first and last)
│   └── out_parties.txt.      # 2500 candidate names (first and last)
├── data/                     # Spreadsheets used during the simulation
│   ├── historical_data.xlsx  # Compact election cycle data, past elections generated once, then updated after each cycle
│   └── seniority.xlsx        # Ongoing roster of seniority in your party, updated after each cycle
├── results/                  # Cached runs of the game, only for viewing by the user
├── constants.py              # Stores hyperparameters and global constants of the game 
├── custom_types.py           # Configures custom types for clean object construction code
├── simulator.py              # Runs election simulations, contains voting logic
├── reporter.py               # For live elections, reports updates and final results to the user
├── data_tracker.py           # Makes dynamic updates to data, stores new data
├── runner.py                 # Driver code, takes in user input, runs game
├── tests/                    # Automated unit and integration test suite
│   ├── test_construction.py  # Tests that all data structures are built correctly
│   ├── test_naming.py        # Tests that naming rules are followed
│   ├── test_seniority.py     # Tests that the seniority process is implemented correctly
│   ├── test_voting.py        # Tests that the election/voting math is correct
│   ├── test_rules.py         # Tests that the rules of the game (flow of gameplay, stop conditions) are followed
│   ├── test_live.py          # Tests that live elections are reported to the user correctly
│   ├── test_storage.py       # Tests that data is stored and/or exported correctly
│   └── test_smoke.py         # Rapid end-to-end integration smoke test
└── README.md                 # Project specification, run documentation, architecture, and usage
```

## 3. Installation & Usage
### Prerequisites
The project requires **Python 3.9+** (tested on Python 3.14) with the following third-party packages:
- `numpy` — vectorized multi-district live election batch simulation
- `openpyxl` — creating, updating, and reading `data/historical_data.xlsx` and `data/seniority.xlsx`

### Installation
Navigate to the project root and install dependencies via `pip`:
```bash
pip3 install numpy openpyxl
```
*(No additional build step is required; all candidate and party name lists are already stored in `names/`.)*

### Running the Simulator
Start the interactive CLI simulation from the project root:
```bash
python3 runner.py
```
During a session, spreadsheets are written to `data/` (`historical_data.xlsx` and `seniority.xlsx`). At the end of a game, you can choose to save those spreadsheets to a timestamped folder inside `results/` or discard them; either choice clears `data/` for the next run.

### Global Hotkeys (Usable at Any Prompt)
- **`Q` or `q`**: Cleanly quit the game at any prompt, wipes `data/` subfolder.
- **`R` or `r`**: Cleanly restart the game at any prompt, wipes `data/` subfolder.

### Running Automated Tests
Run all unit, mathematical, pipeline, smoke, and file export tests:
```bash
python3 -m unittest discover tests
```
For verbose per-test output:
```bash
python3 -m unittest discover tests -v
```

## 4. Personal Experiments / High Scores (Coming Soon)
Here are my general notes/observations from playing each of the following cases of the game:

### a) 2-Party Game
On my first trial of the game (not cached), I realized that it was very difficult for an incumbent to lose a live re-election because platforms of candidates are never changed. In the live election method, the Euclidean distance based probability distribution is deterministically computed, and the random slices can only give a candidate a 60-40 advantage (best case) before considering that distance. Thus, if a candidate has a <40% chance of being elected based on Euclidean distance, they will deterministically lose every time. To address this, I will make sure platforms of opponents who lose are randomly regenerated within their party distribution. Over time, the more moderate platforms will stick. This will fix the seniority backlog that prevented me from advancing past state legislator (if it's easier to lose an election, more people will lose their seniority). 

### b) 4-Party Game
### c) 8-Party Game
