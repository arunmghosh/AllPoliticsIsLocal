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

We know that each state, city, and district has a position vector, and so does each party. Initialize the national position vector as 0.5 on all issues. Compute the Euclidean distances between the population (nation, state, city, or district) position and each party platform. A population is most likely to elect the party closest to their ideology (i.e., the party with the smallest distance from them). Take the reciprocals of these distances so a higher number corresponds to a higher probability of being elected. Standardize these new scores to get a probability distribution.

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
The default election simulation mode is the mode outlined for generating historical data (see above). However, there is a live mode that lets you see election results for the current cycle as they come in.

1. Compute a probability distribution over the candidates
2. Generate random cutpoints for the interval (0,1) to slice it, and give one slice to each candidate
3. Multiply the length of a candidate's slice by that candidate's share of the distribution in step 1
4. Standardize the new lengths to get that candidate's share of the vote
5. Multiply each share by the number of rounds of voting (determined by the number of candidates

Let's walk through those steps in more detail. 

We know that each district has a position vector, and so does each candidate. Compute the Euclidean distances between the district position and each candidate position. A district is most likely to elect the candidate closest to their ideology (i.e., the candidate with the smallest distance from them). Take the reciprocals of these distances so a higher number corresponds to a higher probability of being elected. Standardize these new scores to get a probability distribution.

Assume that there are P parties, so there are P candidates in every election. We want to randomly divide the interval (0,1) into P slices. To do this, we generate a sequence of P - 1 cutpoints. We now have P lengths that sum to 1, which will serve as the initial scores for the candidates. 

But, these scores are completely random and not related to their actual chances of being elected. Thus, we rescale a candidate's score by multiplying it by the candidate's chance of being elected (computed in step 1). 

Since this operation perturbed the probability distribution, we need to standardize the scores again to arrive at the final shares of the vote. For elections with a larger scope than 1 district, these shares are summed over all districts participating in those elections (every district has the same population by design) and standardized one final time.

If there are only 2 parties, then the winner will have at least 50% of the vote. But this system also works for ranked-choice voting. This simulation doesn't actually do multiple rounds or have voters rank candidates. It simulates one round, gets the shares, and multiplies by the number of rounds so the winner is guaranteed to have at least 50%. This represents that over all rounds, at least 50% of voters chose that candidate for one of the rounds. The number of rounds R is determined by P, according to the function R(P) = floor(P/2).

Due to the all politics is local rule, this simulation ignores any effects that the actions that higher level politicians have on the voting decisions of people in the district.
