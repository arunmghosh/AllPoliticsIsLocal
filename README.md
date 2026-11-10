# All Politics Is Local
An interactive election simulation game in which you run for office and progress to higher positions as you win and gain more experience. You have a fifty year career timeline in which to reach the presidency. Lose an election, and you lose the game. You also have the option to simulate prior election data to get an idea of how districts vote and select where / with what party you want to run. 

## 1. Full Problem Specification
### Simulated Country
For simplicity, this simulation enforces a strict hierarchy among levels of office: 
1. Nation
2. State
3. City
4. District

The nation contains 51 states, each state contains 11 cities, each city contains 35 districts, and each district has 10,001 people. I had to choose odd numbers to eliminate the possibility of ties in elections. 

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

### Simulated Politics
Politics is represented by a set of issues, with each have an ideology spectrum represented by the interval (0,1). Low numbers mean a conservative position on the issue, while high numbers mean a liberal position. You have the option to choose up to 3 issues to use for the simulation. While (0,1) is a continuous interval, the position values will be discretized (rounded to the nearest 0.01). 

These issues are debated by parties. Each party has a platform, which is a vector of positions taken on issues. The positions can either be 0.25 (mean of conservative values) or 0.75 (mean of liberal values). Each party must have a unique platform, so if there are I issues, there can be at most 2^I parties. You will have the option to choose how many parties you want, within the range of 2 and 2^I. 

All parties nominate a candidate to run for every position. Candidates each have their own platform, sampled from a random distribution with the rule that they must be liberal or conservative on the same issues that their party is. The conservative range is (0,0.5), and the liberal range is (0.5,1). 

Candidates are elected by people, who each belong to the nation, a state, a city and a district. Instead of each person having their own position vector, each district uses its own position vector to split 10,001 votes among the candidates. Districts are assigned position vectors according the following algorithm:
1. Every state is given a random position vector with each position drawn randomly from (0,1)
2. Every city within each state is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak (highest probability) at the position of the state
3. Every district with each city is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak at the position of the city

The reason this project is called "All Politics Is Local" is because only the district position vectors actually matter for voting. All higher level results are just sums of district results. 

### Simulated Voting
Elections are held every two years, called a cycle. All of the district level positions are up for reelection every cycle. Mayors and members of the House of Representatives serve for two cycles. However, their elections are offset by one cycle. In odd cycles, Mayors are up for election, and in even cycles, house members are up for election. Governors and Senators serve for three cycles, but there are three waves so some are always up for re-election in a given cycle. Split the 51 states into three equal groups of 17 (A, B, C). In cycle 1, group A holds elections for Governor. In cycle 2, group B holds gubernatorial elections, and group C's turn is in cycle 3. Since there are three senators in each state, just assign each one of them a wave (A, B or C) to have their election. Lastly, there is only one President, who serves for four cycles.  

As mentioned before, this simulation doesn't count individual votes, since that is computationally expensive. Instead, it takes the following steps to get a result from a district:

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

### Data Storage
Election results are grouped in cycles. As a reminder, a cycle is 2 years, since there are elections every 2 years. For each office, record the winner of the election or the incumbent if there was no election in that cycle. The results contain:

- "President": Party index
- "Senate": 2D array of party indices with dim 51x3
- "House": 2D array of party indices with dim 51x11
- "Governor": 1D array of 51 party indices
- "State Legislature": 3D array of party indices with dim 51x11x35
- "Mayor": 2D array of party indices with dim 51x11
- "City Council": 3D array of party indices with dim 51x11x35

This yields over 40,000 numbers per cycle. You can play for 25 cycles and request a history of up to 50 cycles before you start, which means an entire game could produce over 3 million numbers. Since you don't want to look at 3 million numbers in Excel spreadsheets, the actual results (per cycle) stored in memory and writable to Excel are what would be most informative for your decisions in the game:

- "President": Party index
- "Senators": 1D array of 3 party indices
- "House": Party index
- "Governor": Party index
- "State Legislature": Party index
- "Mayor": Party index
- "City Council": Party index

In essence, you only care about the data from where you are trying to run, so you can tune your platform and maximize the chances of being elected. The ultimate goal is to become president, so you need the presidential election trends. Along the way to becoming president, you may hold a number of other offices, but those are specific to one state, one city, and one district, so we don't need to keep track of another other areas. You won't know in advance what Senate cycle you will fall into, so all three seats from your state are tracked just in case. This reduces over 40,000 numbers per cycle to just 9! And for a full 75-cycle game, fewer than 700 numbers are stored!

### Natural Party Preference Oscillation Mechanism
In real life, the party in power is often blamed for things that go wrong, and may experience a backlash in the next election. To capture this effect in the simulation, district position vectors will dynamically adjust ahead of each cycle depending on who their incumbent city council representative and state legislator are. Let C be the city council representative and S be the state legislator. Denote C_i and S_i as the respective positions of C and S on issue i. If the district position on that issue is between C_i and S_i, there is no change in position. If it is greater than both, add 0.01. If it is less than both, subtract 0.01. The position values must always be between 0.01 and 0.99 inclusive. 

Due to the all politics is local rule, this simulation ignores any effects that the actions that higher level politicians have on the voting decisions of people in the district. 

### Gameplay
When the game starts, the nation is initialized, and the position vectors for every state, city and district are generated as specified above. You can view the state position vectors and pick your home state (where you will run). 
